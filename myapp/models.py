from django.db import models

STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
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
    certificate = models.TextField()  
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)

    def __str__(self):
        return self.full_name
