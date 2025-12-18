from django import forms
from django.contrib.auth.hashers import make_password
from .models import JobSeeker, JOB_TYPE_CHOICES


class JobSeekerForm(forms.ModelForm):
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm your password'})
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={'placeholder': 'Enter your password'})
    )

    # Multiple selection for job types
    job_type = forms.MultipleChoiceField(
        choices=JOB_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        help_text="Select one or more preferred job types."
    )

    class Meta:
        model = JobSeeker
        fields = [
            'full_name', 'email', 'password', 'confirm_password', 'phone_number',
            'location', 'education', 'work_experience', 'skills', 'certificate',
            'certification_files', 'job_type', 'professional_references', 'profile_picture'
        ]
        widgets = {
            'education': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Degree, Institution, Years'}),
            'work_experience': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Job title, Company, Duration...'}),
            'skills': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Python, JavaScript, Communication, etc.'}),
            'certificate': forms.Textarea(attrs={'rows': 2, 'placeholder': 'AWS Certified, Google Analytics, etc.'}),
            'professional_references': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Name, Position, Company, Contact Info'
            }),
            'profile_picture': forms.FileInput(),
        }
        labels = {
            'full_name': 'Full Name',
            'phone_number': 'Phone Number',
            'location': 'Location',
            'certification_files': 'Certification Proofs (PDF/JPG)',
            'profile_picture': 'Profile Picture',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If editing existing instance, pre-select current job types
        if self.instance.pk and self.instance.job_type:
            selected = [jt.strip() for jt in self.instance.job_type.split(',') if jt.strip()]
            self.fields['job_type'].initial = selected

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            if not (email.endswith('@gmail.com') or email.endswith('@outlook.com')):
                raise forms.ValidationError("Only Gmail or Outlook email addresses are allowed.")
            if self.instance.pk:  # Exclude current instance when editing
                if JobSeeker.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
                    raise forms.ValidationError("This email is already registered.")
            else:
                if JobSeeker.objects.filter(email=email).exists():
                    raise forms.ValidationError("This email is already registered.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")

        if password and confirm:
            if password != confirm:
                self.add_error('confirm_password', "Passwords do not match.")
            elif len(password) < 8:
                self.add_error('password', "Password must be at least 8 characters long.")
            else:
                # Only hash password on creation or when explicitly changed
                if not self.instance.pk or JobSeeker.objects.filter(pk=self.instance.pk, password__startswith='$2b$').exists() is False:
                    cleaned_data['password'] = make_password(password)

        # Handle multiple job types → save as comma-separated string
        selected_job_types = cleaned_data.get('job_type')
        if selected_job_types:
            cleaned_data['job_type'] = ','.join(selected_job_types)
        else:
            cleaned_data['job_type'] = ''

        return cleaned_data


# Optional: Updated simpler registration form (if you want to include more fields later)
class JobSeekerRegisterForm(forms.ModelForm):
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password'})
    )

    # Optional: Add multiple job types even in quick register
    job_type = forms.MultipleChoiceField(
        choices=JOB_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Preferred Job Types",
        help_text="You can select multiple"
    )

    class Meta:
        model = JobSeeker
        fields = ['full_name', 'email', 'password', 'confirm_password', 'skills', 'job_type']
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email'}),
            'skills': forms.Textarea(attrs={'placeholder': 'Your Skills (e.g., Python, React, Teamwork)', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.job_type:
            selected = [jt.strip() for jt in self.instance.job_type.split(',') if jt.strip()]
            self.fields['job_type'].initial = selected

    def clean_email(self):
        email = self.cleaned_data.get('email').lower()
        if not (email.endswith('@gmail.com') or email.endswith('@outlook.com')):
            raise forms.ValidationError("Only Gmail or Outlook email addresses are allowed.")
        if JobSeeker.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")

        if password and confirm:
            if password != confirm:
                self.add_error('confirm_password', "Passwords do not match.")
            elif len(password) < 8:
                self.add_error('password', "Password must be at least 8 characters.")
            else:
                cleaned_data['password'] = make_password(password)

        # Save multiple job types as comma-separated
        selected_job_types = cleaned_data.get('job_type')
        if selected_job_types:
            cleaned_data['job_type'] = ','.join(selected_job_types)
        else:
            cleaned_data['job_type'] = ''

        return cleaned_data