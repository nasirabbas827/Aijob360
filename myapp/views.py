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


def dashboard_view(request):
    jobseeker_id = request.session.get('jobseeker_id')
    if not jobseeker_id:
        messages.warning(request, "Please log in to access the dashboard.")
        return redirect('login')

    jobseeker = JobSeeker.objects.get(id=jobseeker_id)
    return render(request, 'dashboard.html', {'jobseeker': jobseeker})


def logout_view(request):
    auth_logout(request)
    request.session.flush()
    messages.warning(request, "You have been logged out.")
    return redirect('login')

from django.shortcuts import render, redirect
from django.contrib import messages
from .models import JobSeeker

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

        if 'profile_picture' in request.FILES:
            jobseeker.profile_picture = request.FILES['profile_picture']

        jobseeker.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('dashboard')

    return render(request, 'update_profile.html', {'jobseeker': jobseeker})

