from django.shortcuts import render

def index(request):
    return render(request, 'index.html')


import uuid
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from .forms import JobSeekerRegisterForm
from .models import JobSeeker

# Email token storage (temp solution - consider a proper model or field)
email_tokens = {}

def register_view(request):
    if request.method == 'POST':
        form = JobSeekerRegisterForm(request.POST)
        if form.is_valid():
            jobseeker = form.save(commit=False)
            jobseeker.status = 'pending'
            jobseeker.save()

            token = str(uuid.uuid4())
            email_tokens[token] = jobseeker.email

            verify_url = request.build_absolute_uri(f'/verify-email/{token}/')
            send_mail(
                'Verify Your Email - Job 360',
                f'Click the link to verify your email: {verify_url}',
                settings.DEFAULT_FROM_EMAIL,
                [jobseeker.email],
                fail_silently=False,
            )
            messages.success(request, 'Registration successful! Please verify your email to activate your account.')
            return redirect('login')
    else:
        form = JobSeekerRegisterForm()
    return render(request, 'register.html', {'form': form})

def verify_email_view(request, token):
    email = email_tokens.get(token)
    if email:
        try:
            user = JobSeeker.objects.get(email=email)
            user.status = 'approved'
            user.save()
            messages.success(request, 'Email verified successfully. You can now log in.')
        except JobSeeker.DoesNotExist:
            messages.error(request, 'Invalid verification link.')
    else:
        messages.error(request, 'Invalid or expired token.')
    return redirect('login')


from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import check_password
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.sessions.models import Session
from .models import JobSeeker

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email').lower()
        password = request.POST.get('password')
        try:
            user = JobSeeker.objects.get(email=email)
            if user.status != 'approved':
                messages.warning(request, "Your account is not approved yet. Please verify your email.")
            elif check_password(password, user.password):
                request.session['jobseeker_id'] = user.id
                messages.success(request, f"Welcome, {user.full_name}")
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid password.")
        except JobSeeker.DoesNotExist:
            messages.error(request, "Account not found.")
    return render(request, 'login.html')


import http.client
import json
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import JobSeeker

HASDATA_API_KEY = "3597e0b3-9f17-4a26-aa3c-0b825b7b4bdb"

def dashboard_view(request):
    jobseeker_id = request.session.get("jobseeker_id")
    if not jobseeker_id:
        messages.warning(request, "Please log in to access the dashboard.")
        return redirect("login")

    jobseeker = JobSeeker.objects.get(id=jobseeker_id)
    skills = jobseeker.skills.split(",") if jobseeker.skills else []
    jobs = []

    if skills:
        # Take first skill for now
        search_skill = skills[0].strip()

        try:
            conn = http.client.HTTPSConnection("api.hasdata.com")
            headers = {
                "x-api-key": HASDATA_API_KEY,
                "Content-Type": "application/json",
            }

            # dynamic keyword and location (default Lahore for now)
            endpoint = f"/scrape/indeed/listing?keyword={search_skill}&location=Lahore&domain=pk.indeed.com"
            conn.request("GET", endpoint, headers=headers)

            res = conn.getresponse()
            data = res.read().decode("utf-8")

            result = json.loads(data)
            print("=== HASDATA RAW RESPONSE ===")
            print(result)  # Debugging

            jobs = result.get("jobs", [])[:5]  # take top 5 jobs

        except Exception as e:
            print("Error fetching jobs:", e)
            messages.error(request, "Could not fetch jobs right now.")

    else:
        messages.info(request, "Please update your profile with skills to see job recommendations.")

    return render(request, "dashboard.html", {"jobseeker": jobseeker, "jobs": jobs})


import http.client
import json
import urllib.parse
from django.shortcuts import render, redirect
from django.contrib import messages

HASDATA_API_KEY = "3597e0b3-9f17-4a26-aa3c-0b825b7b4bdb"

def job_detail_view(request):
    job_url = request.GET.get("url")  # passed from dashboard template
    job_detail = {}

    if not job_url:
        messages.error(request, "No job URL provided.")
        return redirect("dashboard")

    try:
        # Normalize the job URL to only keep the jk param
        parsed = urllib.parse.urlparse(job_url)
        query = urllib.parse.parse_qs(parsed.query)
        jk = query.get("jk", [None])[0]

        if not jk:
            messages.error(request, "Invalid job link.")
            return redirect("dashboard")

        clean_url = f"https://www.indeed.com/viewjob?jk={jk}"

        # Call HasData API
        conn = http.client.HTTPSConnection("api.hasdata.com")
        headers = {
            "x-api-key": HASDATA_API_KEY,
            "Content-Type": "application/json",
        }
        endpoint = f"/scrape/indeed/job?url={urllib.parse.quote(clean_url)}"
        conn.request("GET", endpoint, headers=headers)

        res = conn.getresponse()
        data = res.read().decode("utf-8")
        job_detail = json.loads(data)

        # Optional: log raw data for debugging
        print("=== JOB DETAIL RESPONSE ===")
        print(json.dumps(job_detail, indent=2))

    except Exception as e:
        print("Error fetching job detail:", e)
        messages.error(request, "Could not fetch job details.")
        return redirect("dashboard")

    return render(request, "job_detail.html", {"job": job_detail.get("job", {}), "meta": job_detail.get("requestMetadata", {})})




import io
import http.client
import json
import urllib.parse
from django.http import FileResponse
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.lib.units import inch
import google.generativeai as genai

from .models import JobSeeker

HASDATA_API_KEY = "3597e0b3-9f17-4a26-aa3c-0b825b7b4bdb"
GEMINI_API_KEY = "AIzaSyBUrKCOXidxC4v-T39EuvvP5GInbOxZ6gI"

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-1.5-flash")

def fetch_job_details(job_url):
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
        data = res.read().decode("utf-8")
        job_detail = json.loads(data)
        return job_detail.get("job", {}), None
    except Exception as e:
        return None, f"Error fetching job details: {str(e)}"

def extract_job_requirements(job_description):
    """Extract key skills and requirements using Gemini API."""
    try:
        prompt = (
            f"Extract the top 5 key skills or qualifications from the following job description. "
            f"Return a concise list of skills (e.g., ['Python', 'JavaScript', 'Project Management']). "
            f"Job Description: {job_description[:2000]}"  # Limit length for API
        )
        response = model.generate_content(prompt)
        skills = response.text.strip().split("\n")[:5]
        return [skill.strip(" *-") for skill in skills if skill.strip()]
    except Exception as e:
        print(f"Error extracting requirements with Gemini: {e}")
        return []

def generate_tailored_objective(job_title, company, job_requirements, jobseeker):
    """Generate a tailored career objective using Gemini API."""
    try:
        prompt = (
            f"Write a concise career objective (50-70 words) for a resume tailored to a {job_title} position at {company}. "
            f"Incorporate these job requirements: {', '.join(job_requirements[:3])}. "
            f"Use the candidate's job type ({jobseeker.job_type.replace('_', ' ').title()}) and skills "
            f"({jobseeker.skills[:100]}...). Ensure the tone is professional and ATS-friendly."
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Error generating objective with Gemini: {e}")
        return (
            f"Highly motivated {jobseeker.job_type.replace('_', ' ').title()} professional seeking a {job_title} "
            f"position at {company}. Skilled in {', '.join(job_requirements[:3] or jobseeker.skills.split(',')[:1])} "
            f"with a proven track record in {jobseeker.work_experience[:50] + '...' if jobseeker.work_experience else 'relevant projects'}."
        )

def generate_tailored_experience(work_experience, job_requirements, job_title):
    """Generate tailored work experience bullet points using Gemini API."""
    try:
        prompt = (
            f"Based on the candidate's work experience: {work_experience[:800]}\n"
            f"And job requirements for {job_title}: {', '.join(job_requirements[:5])}\n"
            f"Generate 4-6 professional bullet points highlighting relevant achievements and experiences. "
            f"Start each with a strong action verb (e.g., 'Led', 'Developed', 'Optimized'). "
            f"Make them quantifiable and tailored to the job. Ensure ATS-friendly language."
        )
        response = model.generate_content(prompt)
        bullet_points = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
        return bullet_points[:6]  # Limit to 6
    except Exception as e:
        print(f"Error generating tailored experience with Gemini: {e}")
        # Fallback: Split original experience into bullets
        lines = work_experience.split("\n")
        return [f"• {line.strip()}" for line in lines if line.strip()][:6]

def generate_resume_view(request):
    if request.method == "POST":
        job_url = request.POST.get("job_url")
        if not job_url:
            messages.error(request, "No job URL provided.")
            return redirect("dashboard")

        # Check session for logged-in jobseeker
        jobseeker_id = request.session.get("jobseeker_id")
        if not jobseeker_id:
            messages.warning(request, "Please log in to generate your resume.")
            return redirect("login")

        # Fetch JobSeeker instance
        jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)

        # Fetch job details
        job, error = fetch_job_details(job_url)
        if error:
            messages.error(request, error)
            return redirect("dashboard")

        # Extract job requirements and generate content
        job_description = job.get("description", "")
        job_title = job.get("title", "Unknown Position")
        company = job.get("company", "Unknown Company")
        job_requirements = extract_job_requirements(job_description)
        objective = generate_tailored_objective(job_title, company, job_requirements, jobseeker)
        tailored_experience = generate_tailored_experience(jobseeker.work_experience, job_requirements, job_title)

        # Create PDF in memory
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            rightMargin=0.75*inch, leftMargin=0.75*inch,
            topMargin=1*inch, bottomMargin=0.75*inch
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name="Header", fontSize=24, leading=28, alignment=TA_CENTER,
            textColor=colors.HexColor("#1e293b"), spaceAfter=12, fontName="Helvetica-Bold"
        ))
        styles.add(ParagraphStyle(
            name="SubHeader", fontSize=12, leading=14, alignment=TA_CENTER,
            textColor=colors.HexColor("#64748b"), spaceAfter=24, fontName="Helvetica"
        ))
        styles.add(ParagraphStyle(
            name="SectionTitle", fontSize=16, leading=18, spaceAfter=12,
            textColor=colors.HexColor("#3b82f6"), fontName="Helvetica-Bold",
            alignment=TA_LEFT, leftIndent=0
        ))
        styles.add(ParagraphStyle(
            name="CustomBodyText", fontSize=11, leading=14, spaceAfter=8,
            textColor=colors.HexColor("#334155"), fontName="Helvetica",
            alignment=TA_LEFT, leftIndent=20  # Indent for bullets
        ))
        styles.add(ParagraphStyle(
            name="CustomNormal", fontSize=11, leading=14, spaceAfter=0,
            textColor=colors.HexColor("#334155"), fontName="Helvetica"
        ))

        elements = []

        # Header
        elements.append(Paragraph(jobseeker.full_name, styles["Header"]))
        contact_info = f"{jobseeker.email} | {jobseeker.phone_number} | {jobseeker.location}"
        elements.append(Paragraph(contact_info, styles["SubHeader"]))
        elements.append(Spacer(1, 0.1*inch))

        # Horizontal line under header
        elements.append(Paragraph("<hr width='100%' height='1' color='#e2e8f0'/>", styles["CustomNormal"]))

        # Professional Summary (formerly Objective)
        elements.append(Paragraph("Professional Summary", styles["SectionTitle"]))
        elements.append(Paragraph(objective.replace("\n", "<br/>"), styles["CustomBodyText"]))
        elements.append(Spacer(1, 18))

        # Two-column layout for Skills and Contact Info (improved structure)
        skills_list = [skill.strip() for skill in jobseeker.skills.split(",") if skill.strip()][:6]
        skills_rows = [[Paragraph("Core Skills", styles["SectionTitle"])]] + [[Paragraph(f"• {skill}", styles["CustomBodyText"])] for skill in skills_list]
        contact_rows = [
            [Paragraph("Contact Details", styles["SectionTitle"])],
            [Paragraph(f"Email: {jobseeker.email}", styles["CustomBodyText"])],
            [Paragraph(f"Phone: {jobseeker.phone_number}", styles["CustomBodyText"])],
            [Paragraph(f"Location: {jobseeker.location}", styles["CustomBodyText"])],
            [Paragraph(f"Job Type: {jobseeker.job_type.replace('_', ' ').title()}", styles["CustomBodyText"])]
        ]

        # Pad rows to match length
        max_rows = max(len(skills_rows), len(contact_rows))
        skills_rows += [[Paragraph("", styles["CustomNormal"])] for _ in range(max_rows - len(skills_rows))]
        contact_rows += [[Paragraph("", styles["CustomNormal"])] for _ in range(max_rows - len(contact_rows))]

        table_data = []
        for i in range(max_rows):
            left_cell = skills_rows[i][0]
            right_cell = contact_rows[i][0]
            table_data.append([left_cell, right_cell])

        table = Table(table_data, colWidths=[3.25*inch, 3.25*inch])
        table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),  # Subtle grid for professionalism
        ]))
        elements.append(table)
        elements.append(Spacer(1, 18))

        # Tailored Work Experience (Gemini-generated)
        elements.append(Paragraph("Professional Experience", styles["SectionTitle"]))
        for exp in tailored_experience:
            elements.append(Paragraph(exp, styles["CustomBodyText"]))
        elements.append(Spacer(1, 18))

        # Education
        elements.append(Paragraph("Education", styles["SectionTitle"]))
        elements.append(Paragraph(jobseeker.education.replace("\n", "<br/>"), styles["CustomBodyText"]))
        elements.append(Spacer(1, 18))

        # Certificates
        if jobseeker.certificate:
            elements.append(Paragraph("Certifications", styles["SectionTitle"]))
            certs_list = [cert.strip() for cert in jobseeker.certificate.split(",") if cert.strip()]
            for cert in certs_list:
                elements.append(Paragraph(f"• {cert}", styles["CustomBodyText"]))
            elements.append(Spacer(1, 18))

        # Professional References
        if jobseeker.professional_references:
            elements.append(Paragraph("Professional References", styles["SectionTitle"]))
            ref_lines = [ref.strip() for ref in jobseeker.professional_references.split("\n") if ref.strip()]
            for ref in ref_lines:
                elements.append(Paragraph(f"• {ref}", styles["CustomBodyText"]))
            elements.append(Spacer(1, 18))

        # Target Job
        elements.append(Paragraph("Application Target", styles["SectionTitle"]))
        target_job = f"Tailored for: {job_title} | {company} | {job_url}"
        elements.append(Paragraph(target_job, styles["CustomBodyText"]))

        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f"{jobseeker.full_name}_Resume_{job_title.replace(' ', '_')}.pdf")

    return redirect("dashboard")


def logout_view(request):
    auth_logout(request)
    request.session.flush()
    messages.warning(request, "You have been logged out.")
    return redirect('login')

# views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import JobSeeker, JOB_TYPE_CHOICES  # Import JOB_TYPE_CHOICES

def update_profile_view(request):
    jobseeker_id = request.session.get('jobseeker_id')
    if not jobseeker_id:
        messages.error(request, "Please log in to update your profile.")
        return redirect('login')

    jobseeker = JobSeeker.objects.get(id=jobseeker_id)

    if request.method == 'POST':
        jobseeker.full_name = request.POST.get('full_name')
        jobseeker.email = request.POST.get('email')
        jobseeker.phone_number = request.POST.get('phone_number')
        jobseeker.location = request.POST.get('location')
        jobseeker.education = request.POST.get('education')
        jobseeker.work_experience = request.POST.get('work_experience')
        jobseeker.skills = request.POST.get('skills')
        jobseeker.certificate = request.POST.get('certificate')
        jobseeker.job_type = request.POST.get('job_type')
        jobseeker.professional_references = request.POST.get('professional_references')

        if 'profile_picture' in request.FILES:
            jobseeker.profile_picture = request.FILES['profile_picture']

        jobseeker.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('update_profile')

    # Pass JOB_TYPE_CHOICES to the template
    return render(request, 'update_profile.html', {
        'jobseeker': jobseeker,
        'job_type_choices': JOB_TYPE_CHOICES
    })


from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from .models import SavedJob, JobSeeker

def toggle_save_job(request, job_url):
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


from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import SavedJob, JobSeeker

def saved_jobs_view(request):
    jobseeker_id = request.session.get("jobseeker_id")
    if not jobseeker_id:
        messages.warning(request, "Please log in to view saved jobs.")
        return redirect("login")

    jobseeker = get_object_or_404(JobSeeker, id=jobseeker_id)
    saved_jobs = SavedJob.objects.filter(jobseeker=jobseeker).order_by("-saved_at")

    return render(request, "saved_jobs.html", {"saved_jobs": saved_jobs})
