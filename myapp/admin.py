from django.contrib import admin
from .models import JobSeeker

@admin.register(JobSeeker)
class JobSeekerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone_number', 'location', 'status')
    list_filter = ('status', 'location')
    search_fields = ('full_name', 'email', 'skills', 'location')
