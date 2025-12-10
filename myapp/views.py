# views.py
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


def dashboard_view(request):
    """
    Display personalized job recommendations using TF-IDF similarity.
    """
    jobseeker_id = request.session.get("jobseeker_id")
    if not jobseeker_id:
        messages.warning(request, "Please log in to access the dashboard.")
        return redirect("login")

    jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)

    # Check if profile is complete
    required_fields = [
        jobseeker.phone_number,
        jobseeker.location,
        jobseeker.education,
        jobseeker.work_experience,
        jobseeker.skills,
    ]
    if not all(required_fields):
        messages.info(request, "Please complete your profile to get personalized job recommendations.")
        return redirect("update_profile")

    location = jobseeker.location.strip() or "Lahore"
    user_skills_list = [s.strip() for s in jobseeker.skills.split(",") if s.strip()]

    if not user_skills_list:
        messages.warning(request, "No skills added yet. Please update your profile.")
        return redirect("update_profile")

    user_skills_text = " ".join(user_skills_list).lower()

    jobs = []
    try:
        conn = http.client.HTTPSConnection("api.hasdata.com")
        headers = {
            "x-api-key": HASDATA_API_KEY,
            "Content-Type": "application/json",
        }

        # Use the primary skill as search keyword
        search_keyword = user_skills_list[0]
        endpoint = (
            f"/scrape/indeed/listing"
            f"?keyword={urllib.parse.quote(search_keyword)}"
            f"&location={urllib.parse.quote(location)}"
            f"&domain=pk.indeed.com"
            f"&limit=20"
        )

        conn.request("GET", endpoint, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))

        raw_jobs = data.get("jobs", [])[:20]

        # Prepare job descriptions for similarity matching
        job_descriptions = [
            (job.get("title", "") + " " + job.get("description", "")).lower()
            for job in raw_jobs
        ]

        if job_descriptions:
            vectorizer = TfidfVectorizer(stop_words="english")
            tfidf_matrix = vectorizer.fit_transform([user_skills_text] + job_descriptions)
            similarity_scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

            for job, score in zip(raw_jobs, similarity_scores):
                job["match_score"] = round(score * 100, 1)
                jobs.append(job)

            jobs.sort(key=lambda x: x["match_score"], reverse=True)

    except Exception as e:
        print(f"Error fetching jobs: {e}")
        messages.error(request, "Could not fetch jobs right now. Please try again later.")

    context = {
        "jobseeker": jobseeker,
        "jobs": jobs,
        "location": location,
    }
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
        jobseeker.email = request.POST.get('email', jobseeker.email)
        jobseeker.phone_number = request.POST.get('phone_number', jobseeker.phone_number)
        jobseeker.location = request.POST.get('location', jobseeker.location)
        jobseeker.education = request.POST.get('education', jobseeker.education)
        jobseeker.work_experience = request.POST.get('work_experience', jobseeker.work_experience)
        jobseeker.skills = request.POST.get('skills', jobseeker.skills)
        jobseeker.certificate = request.POST.get('certificate', jobseeker.certificate)
        jobseeker.job_type = request.POST.get('job_type', jobseeker.job_type)
        jobseeker.professional_references = request.POST.get('professional_references', jobseeker.professional_references)

        if 'profile_picture' in request.FILES:
            jobseeker.profile_picture = request.FILES['profile_picture']

        jobseeker.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('update_profile')

    return render(request, 'update_profile.html', {
        'jobseeker': jobseeker,
        'job_type_choices': JOB_TYPE_CHOICES
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


# views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages

# ... other imports ...

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