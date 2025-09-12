from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('verify-email/<str:token>/', views.verify_email_view, name='verify_email'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('update-profile/', views.update_profile_view, name='update_profile'),
    path("job-detail/", views.job_detail_view, name="job_detail"),
    path("generate-resume/", views.generate_resume_view, name="generate_resume"),
    path("toggle-save-job/<path:job_url>/", views.toggle_save_job, name="toggle_save_job"),
    path("saved-jobs/", views.saved_jobs_view, name="saved_jobs"),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
