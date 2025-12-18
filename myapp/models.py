from django.db import models
from django.utils import timezone


from django.db import models
from django.utils import timezone

STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
)

JOB_TYPE_CHOICES = (
    ('full_time', 'Full Time'),
    ('part_time', 'Part Time'),
    ('remote', 'Remote'),
    ('contract', 'Contract'),
    ('internship', 'Internship'),
)

class JobSeeker(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    location = models.CharField(max_length=100)
    education = models.TextField()
    work_experience = models.TextField()
    skills = models.TextField()
    
    # Kept for manual entry of certification names
    certificate = models.TextField(blank=True, help_text="List your certifications (e.g., AWS Certified, Google Analytics)")
    
    # New: Upload certification proofs (PDF, JPG, JPEG, PNG)
    certification_files = models.FileField(
        upload_to='certifications/',
        null=True,
        blank=True,
        help_text="Upload proof of certifications (PDF, JPG, JPEG, PNG)"
    )
    
    # Changed to allow multiple job types
    job_type = models.CharField(
        max_length=200,
        blank=True,
        help_text="Comma-separated list of preferred job types"
    )
    
    professional_references = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)

    def __str__(self):
        return self.full_name

    def get_job_type_list(self):
        """Helper to get list of selected job types"""
        if self.job_type:
            return [jt.strip() for jt in self.job_type.split(',') if jt.strip()]
        return []

    def get_job_type_display_list(self):
        """Return human-readable job type labels"""
        mapping = dict(JOB_TYPE_CHOICES)
        selected = self.get_job_type_list()
        return [mapping.get(jt, jt) for jt in selected]



class SavedJob(models.Model):
    jobseeker = models.ForeignKey("JobSeeker", on_delete=models.CASCADE, related_name="saved_jobs")
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    job_type = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField()
    job_url = models.URLField()
    saved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("jobseeker", "job_url")  # prevent duplicate saves

    def __str__(self):
        return f"{self.title} at {self.company} ({self.jobseeker.full_name})"
