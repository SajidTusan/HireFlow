from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from recruiting import views

urlpatterns = [path("admin/", admin.site.urls), path("login/", LoginView.as_view(template_name="registration/login.html", redirect_authenticated_user=True), name="login"), path("logout/", LogoutView.as_view(next_page="login"), name="logout"), path("", views.dashboard, name="dashboard"), path("jobs/", views.jobs, name="jobs"), path("jobs/new/", views.job_create, name="job_create"), path("jobs/<int:job_id>/", views.job_detail, name="job_detail"), path("jobs/<int:job_id>/shortlist/", views.shortlist, name="shortlist"), path("jobs/<int:job_id>/invite/", views.invite_shortlisted, name="invite"), path("jobs/<int:job_id>/export/", views.export_shortlist, name="export_shortlist"), path("candidates/", views.candidates, name="candidates"), path("candidates/upload/", views.candidate_upload, name="candidate_upload"), path("candidates/<int:candidate_id>/", views.candidate_detail, name="candidate_detail"), path("settings/", views.settings_page, name="settings")]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
