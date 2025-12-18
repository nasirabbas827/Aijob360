"""
Views for the JobSeeker application.
Handles user registration, email verification, authentication, dashboard with job recommendations,
resume generation, profile updates, job saving, and more.
"""

import uuid
import json
import urllib.parse
import http.client
import io
from typing import List, Dict, Tuple, Optional

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.contrib.auth import logout as auth_logout
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.conf import settings
from django.http import FileResponse
from django.views.decorators.http import require_POST

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.lib.units import inch

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import google.generativeai as genai

from .forms import JobSeekerRegisterForm
from .models import JobSeeker, SavedJob, JOB_TYPE_CHOICES

# API Keys (consider moving to environment variables in production)
HASDATA_API_KEY = "dd622e93-5309-4504-ab2c-a2e43604c5dd"
GEMINI_API_KEY = "AIzaSyBUrKCOXidxC4v-T39EuvvP5GInbOxZ6gI"

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL = genai.GenerativeModel("models/gemini-1.5-flash")

# Temporary in-memory token storage (use Redis or a model in production)
email_tokens: Dict[str, str] = {}


# ----------------------- Public Views -----------------------


def index(request):
    """Render the homepage."""
    return render(request, 'index.html')


def register_view(request):
    """
    Handle job seeker registration and send email verification link.
    """
    if request.method == 'POST':
        form = JobSeekerRegisterForm(request.POST)
        if form.is_valid():
            jobseeker = form.save(commit=False)
            jobseeker.status = 'pending'
            jobseeker.save()

            # Generate and store verification token
            token = str(uuid.uuid4())
            email_tokens[token] = jobseeker.email

            # Build verification URL
            verify_url = request.build_absolute_uri(f'/verify-email/{token}/')

            # Send verification email
            send_mail(
                subject='Verify Your Email - Job 360',
                message=f'Click the link to verify your email: {verify_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[jobseeker.email],
                fail_silently=False,
            )

            messages.success(request, 'Registration successful! Please check your email to verify your account.')
            return redirect('login')
    else:
        form = JobSeekerRegisterForm()

    return render(request, 'register.html', {'form': form})


def verify_email_view(request, token):
    """
    Verify the email using the provided token and activate the account.
    """
    email = email_tokens.get(token)
    if email:
        try:
            jobseeker = JobSeeker.objects.get(email=email)
            jobseeker.status = 'approved'
            jobseeker.save()
            messages.success(request, 'Email verified successfully. You can now log in.')
            # Clean up token
            email_tokens.pop(token, None)
        except JobSeeker.DoesNotExist:
            messages.error(request, 'Invalid verification link.')
    else:
        messages.error(request, 'Invalid or expired token.')

    return redirect('login')


def login_view(request):
    """
    Authenticate job seeker using email and password.
    """
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        try:
            jobseeker = JobSeeker.objects.get(email=email)

            if jobseeker.status != 'approved':
                messages.warning(request, "Your account is not approved yet. Please verify your email.")
            elif check_password(password, jobseeker.password):
                request.session['jobseeker_id'] = jobseeker.id
                messages.success(request, f"Welcome, {jobseeker.full_name}!")
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid password.")
        except JobSeeker.DoesNotExist:
            messages.error(request, "Account not found.")

    return render(request, 'login.html')


def logout_view(request):
    """Log out the user and clear the session."""
    auth_logout(request)
    request.session.flush()
    messages.warning(request, "You have been logged out.")
    return redirect('login')


# ----------------------- Protected Views -----------------------


import http.client
import urllib.parse
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from .models import JobSeeker, JOB_TYPE_CHOICES


def dashboard_view(request):
    """
    Dashboard with manual job search + personalized recommendations fallback.
    Supports search by keyword, location, and multiple job types.
    """
    jobseeker_id = request.session.get("jobseeker_id")
    if not jobseeker_id:
        messages.warning(request, "Please log in to access the dashboard.")
        return redirect("login")

    jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)

    # Base context
    context = {
        "jobseeker": jobseeker,
        "job_type_choices": JOB_TYPE_CHOICES,
        "current_location": jobseeker.location.strip() or "Lahore",
    }

    # Get search parameters
    search_keyword = request.GET.get("keyword", "").strip()
    search_location = request.GET.get("location", "").strip() or context["current_location"]
    selected_job_types = request.GET.getlist("job_type")  # Multiple selection

    jobs = []
    search_performed = bool(search_keyword or selected_job_types)

    try:
        conn = http.client.HTTPSConnection("api.hasdata.com")
        headers = {
            "x-api-key": HASDATA_API_KEY,
            "Content-Type": "application/json",
        }

        # Determine search keyword
        if search_keyword:
            keyword_to_search = search_keyword
        else:
            # Fallback to personalized: use first skill
            user_skills = [s.strip() for s in jobseeker.skills.split(",") if s.strip()]
            if not user_skills:
                messages.info(request, "Add skills to your profile for better recommendations.")
                context.update({"jobs": jobs, "location": search_location})
                return render(request, "dashboard.html", context)
            keyword_to_search = user_skills[0]

        # Build endpoint
        endpoint = (
            f"/scrape/indeed/listing"
            f"?keyword={urllib.parse.quote(keyword_to_search)}"
            f"&location={urllib.parse.quote(search_location)}"
            f"&domain=pk.indeed.com"
            f"&limit=30"
        )

        conn.request("GET", endpoint, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        raw_jobs = data.get("jobs", [])[:30]

        # Prepare full text for TF-IDF (title + description)
        job_texts = [
            (job.get("title", "") + " " + job.get("description", "")).lower()
            for job in raw_jobs
        ]

        # If user has skills, compute match score
        if jobseeker.skills.strip():
            user_skills_text = " ".join(
                [s.strip() for s in jobseeker.skills.split(",") if s.strip()]
            ).lower()

            if job_texts:
                vectorizer = TfidfVectorizer(stop_words="english")
                tfidf_matrix = vectorizer.fit_transform([user_skills_text] + job_texts)
                similarity_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

                for job, score in zip(raw_jobs, similarity_scores):
                    job["match_score"] = round(score * 100, 1)
            else:
                for job in raw_jobs:
                    job["match_score"] = None
        else:
            for job in raw_jobs:
                job["match_score"] = None

        # Filter by selected job types (if any)
        if selected_job_types:
            filtered_jobs = []
            for job in raw_jobs:
                job_type_lower = job.get("job_type", "").lower()
                if any(jt.lower() in job_type_lower for jt in selected_job_types):
                    filtered_jobs.append(job)
                # Also check common variations
                elif any(
                    jt.lower().replace("_", " ") in job_type_lower or
                    jt.lower().replace("_", "-") in job_type_lower
                    for jt in selected_job_types
                ):
                    filtered_jobs.append(job)
            jobs = filtered_jobs
        else:
            jobs = raw_jobs

        # Sort by match score if available
        if any(j.get("match_score") is not None for j in jobs):
            jobs.sort(key=lambda x: x.get("match_score", 0), reverse=True)

    except Exception as e:
        print(f"Error fetching jobs: {e}")
        messages.error(request, "Unable to fetch jobs at the moment. Please try again later.")
        jobs = []

    context.update({
        "jobs": jobs,
        "location": search_location,
        "search_keyword": search_keyword,
        "selected_job_types": selected_job_types,
        "search_performed": search_performed,
    })

    return render(request, "dashboard.html", context)



def job_detail_view(request):
    """Display detailed information for a specific job."""
    job_url = request.GET.get("url")
    if not job_url:
        messages.error(request, "No job URL provided.")
        return redirect("dashboard")

    try:
        parsed = urllib.parse.urlparse(job_url)
        query = urllib.parse.parse_qs(parsed.query)
        jk = query.get("jk", [None])[0]

        if not jk:
            messages.error(request, "Invalid job link.")
            return redirect("dashboard")

        clean_url = f"https://www.indeed.com/viewjob?jk={jk}"

        conn = http.client.HTTPSConnection("api.hasdata.com")
        headers = {"x-api-key": HASDATA_API_KEY, "Content-Type": "application/json"}
        endpoint = f"/scrape/indeed/job?url={urllib.parse.quote(clean_url)}"

        conn.request("GET", endpoint, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))

        job_detail = data.get("job", {})
        metadata = data.get("requestMetadata", {})

    except Exception as e:
        print(f"Error fetching job detail: {e}")
        messages.error(request, "Could not fetch job details.")
        return redirect("dashboard")

    return render(request, "job_detail.html", {"job": job_detail, "meta": metadata})


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import JobSeeker, JOB_TYPE_CHOICES

def update_profile_view(request):
    """
    Allow logged-in job seekers to update their profile information.
    """
    jobseeker_id = request.session.get('jobseeker_id')
    if not jobseeker_id:
        messages.error(request, "Please log in to update your profile.")
        return redirect('login')

    jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)

    if request.method == 'POST':
        jobseeker.full_name = request.POST.get('full_name', jobseeker.full_name)
        jobseeker.phone_number = request.POST.get('phone_number', jobseeker.phone_number)
        jobseeker.location = request.POST.get('location', jobseeker.location)
        jobseeker.education = request.POST.get('education', jobseeker.education)
        jobseeker.work_experience = request.POST.get('work_experience', jobseeker.work_experience)
        jobseeker.skills = request.POST.get('skills', jobseeker.skills)
        jobseeker.certificate = request.POST.get('certificate', jobseeker.certificate)
        jobseeker.professional_references = request.POST.get('professional_references', jobseeker.professional_references)

        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            jobseeker.profile_picture = request.FILES['profile_picture']

        # Handle certification file upload
        if 'certification_files' in request.FILES:
            jobseeker.certification_files = request.FILES['certification_files']

        # Handle multiple job types (from <select multiple>)
        job_types_selected = request.POST.getlist('job_type')
        if job_types_selected:
            jobseeker.job_type = ','.join(job_types_selected)
        else:
            jobseeker.job_type = ''

        jobseeker.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('update_profile')

    return render(request, 'update_profile.html', {
        'jobseeker': jobseeker,
        'job_type_choices': JOB_TYPE_CHOICES,
    })


@require_POST
def toggle_save_job(request, job_url):
    """Save or unsave a job for the logged-in user."""
    jobseeker_id = request.session.get("jobseeker_id")
    if not jobseeker_id:
        messages.warning(request, "Please log in to save jobs.")
        return redirect("login")

    jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)

    title = request.POST.get("title")
    company = request.POST.get("company")
    location = request.POST.get("location")
    job_type = request.POST.get("job_type")
    description = request.POST.get("description")

    existing = SavedJob.objects.filter(jobseeker=jobseeker, job_url=job_url).first()

    if existing:
        existing.delete()
        messages.info(request, "Job removed from saved list.")
    else:
        SavedJob.objects.create(
            jobseeker=jobseeker,
            title=title,
            company=company,
            location=location,
            job_type=job_type,
            description=description,
            job_url=job_url,
        )
        messages.success(request, "Job saved successfully!")

    return redirect(request.META.get("HTTP_REFERER", "dashboard"))


def saved_jobs_view(request):
    """Display all jobs saved by the current user."""
    jobseeker_id = request.session.get("jobseeker_id")
    if not jobseeker_id:
        messages.warning(request, "Please log in to view saved jobs.")
        return redirect("login")

    jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)
    saved_jobs = SavedJob.objects.filter(jobseeker=jobseeker).order_by("-saved_at")

    return render(request, "saved_jobs.html", {"saved_jobs": saved_jobs})


# ----------------------- Resume Generation -----------------------


def fetch_job_details(job_url: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Fetch job details from HasData API."""
    try:
        parsed = urllib.parse.urlparse(job_url)
        query = urllib.parse.parse_qs(parsed.query)
        jk = query.get("jk", [None])[0]
        if not jk:
            return None, "Invalid job link."

        clean_url = f"https://www.indeed.com/viewjob?jk={jk}"
        conn = http.client.HTTPSConnection("api.hasdata.com")
        headers = {"x-api-key": HASDATA_API_KEY, "Content-Type": "application/json"}
        endpoint = f"/scrape/indeed/job?url={urllib.parse.quote(clean_url)}"
        conn.request("GET", endpoint, headers=headers)

        res = conn.getresponse()
        data = json.loads(res.read().decode("utf-8"))
        return data.get("job", {}), None
    except Exception as e:
        return None, f"Error fetching job details: {str(e)}"


def extract_job_requirements(job_description: str) -> List[str]:
    """Use Gemini to extract top 5 key skills/requirements."""
    try:
        prompt = (
            f"Extract the top 5 key skills or qualifications from the following job description. "
            f"Return a concise list of skills (e.g., ['Python', 'JavaScript', 'Project Management']). "
            f"Job Description: {job_description[:2000]}"
        )
        response = GEMINI_MODEL.generate_content(prompt)
        skills = response.text.strip().split("\n")[:5]
        return [skill.strip(" *-") for skill in skills if skill.strip()]
    except Exception as e:
        print(f"Error extracting requirements: {e}")
        return []


def generate_tailored_objective(job_title: str, company: str, requirements: List[str], jobseeker: JobSeeker) -> str:
    """Generate a tailored professional summary using Gemini."""
    try:
        prompt = (
            f"Write a concise career objective (50-70 words) for a resume tailored to a {job_title} position at {company}. "
            f"Incorporate these job requirements: {', '.join(requirements[:3])}. "
            f"Use the candidate's job type ({jobseeker.job_type.replace('_', ' ').title()}) and skills "
            f"({jobseeker.skills[:100]}...). Ensure the tone is professional and ATS-friendly."
        )
        response = GEMINI_MODEL.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating objective: {e}")
        return (
            f"Highly motivated {jobseeker.job_type.replace('_', ' ').title()} professional seeking a {job_title} "
            f"position at {company}. Skilled in {', '.join(requirements[:3] or jobseeker.skills.split(',')[:1])} "
            f"with a proven track record in {jobseeker.work_experience[:50] + '...' if jobseeker.work_experience else 'relevant projects'}."
        )


def generate_tailored_experience(work_experience: str, requirements: List[str], job_title: str) -> List[str]:
    """Generate tailored work experience bullet points using Gemini."""
    try:
        prompt = (
            f"Based on the candidate's work experience: {work_experience[:800]}\n"
            f"And job requirements for {job_title}: {', '.join(requirements[:5])}\n"
            f"Generate 4-6 professional bullet points highlighting relevant achievements and experiences. "
            f"Start each with a strong action verb (e.g., 'Led', 'Developed', 'Optimized'). "
            f"Make them quantifiable and tailored to the job. Ensure ATS-friendly language."
        )
        response = GEMINI_MODEL.generate_content(prompt)
        bullets = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
        return bullets[:6]
    except Exception as e:
        print(f"Error generating experience: {e}")
        lines = work_experience.split("\n")
        return [f"• {line.strip()}" for line in lines if line.strip()][:6]


def generate_resume_view(request):
    if request.method != "POST":
        return redirect("dashboard")

    job_url = request.POST.get("job_url")
    if not job_url:
        messages.error(request, "No job URL provided.")
        return redirect("dashboard")

    jobseeker_id = request.session.get("jobseeker_id")
    if not jobseeker_id:
        messages.warning(request, "Please log in to generate your resume.")
        return redirect("login")

    jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)

    # Fetch job details (same as before)
    job, error = fetch_job_details(job_url)
    if error:
        messages.error(request, error)
        return redirect("dashboard")

    job_title = job.get("title", "Unknown Position")
    company = job.get("company", "Unknown Company")

    # Generate tailored content using Gemini
    job_description = job.get("description", "")
    requirements = extract_job_requirements(job_description)
    objective = generate_tailored_objective(job_title, company, requirements, jobseeker)
    tailored_experience = generate_tailored_experience(jobseeker.work_experience, requirements, job_title)

    # Prepare skills list
    skills_list = [s.strip() for s in jobseeker.skills.split(",") if s.strip()][:8]

    # Prepare certificates
    certificates = [c.strip() for c in jobseeker.certificate.split(",") if c.strip()] if jobseeker.certificate else []

    # Render the HTML resume
    context = {
        "jobseeker": jobseeker,
        "job_title": job_title,
        "company": company,
        "objective": objective,
        "tailored_experience": tailored_experience,
        "skills_list": skills_list,
        "certificates": certificates,
    }

    return render(request, "resume.html", context)