from django.contrib import admin
from .models import JobSeeker, SavedJob


@admin.register(JobSeeker)
class JobSeekerAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "phone_number",
        "location",
        "job_type",
        "status",
    )
    search_fields = ("full_name", "email", "skills", "location")
    list_filter = ("status", "job_type", "location")
    ordering = ("full_name",)


@admin.register(SavedJob)
class SavedJobAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company",
        "location",
        "job_type",
        "jobseeker",
        "saved_at",
    )
    search_fields = ("title", "company", "location", "jobseeker__full_name")
    list_filter = ("job_type", "saved_at")
    ordering = ("-saved_at",)
