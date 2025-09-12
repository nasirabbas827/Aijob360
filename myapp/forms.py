from django import forms
from .models import JobSeeker
from django.contrib.auth.hashers import make_password

class JobSeekerForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput())
    password = forms.CharField(widget=forms.PasswordInput())

    class Meta:
        model = JobSeeker
        fields = [
            'full_name', 'email', 'password', 'confirm_password', 'phone_number',
            'location', 'education', 'work_experience', 'skills', 'certificate',
            'job_type', 'professional_references'
        ]
        widgets = {
            'education': forms.Textarea(attrs={'rows': 3}),
            'work_experience': forms.Textarea(attrs={'rows': 3}),
            'certificate': forms.Textarea(attrs={'rows': 2}),
            'professional_references': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Name, Position, Company, Contact Info'}),
            'job_type': forms.Select(),
        }

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
            elif len(password) < 6:
                self.add_error('password', "Password must be at least 6 characters.")
            else:
                cleaned_data['password'] = make_password(password)
        return cleaned_data

class JobSeekerRegisterForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Confirm Password'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password'}))

    class Meta:
        model = JobSeeker
        fields = ['full_name', 'email', 'password', 'confirm_password', 'skills']
        widgets = {
            'full_name': forms.TextInput(attrs={'placeholder': 'Full Name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'Email'}),
            'skills': forms.Textarea(attrs={'placeholder': 'Your Skills', 'rows': 3}),
        }

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
            elif len(password) < 6:
                self.add_error('password', "Password must be at least 6 characters.")
            else:
                cleaned_data['password'] = make_password(password)
        return cleaned_data