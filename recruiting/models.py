from django.db import models

class Job(models.Model):
    title = models.CharField(max_length=160)
    department = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    required_skills = models.TextField(help_text="Comma separated skills")
    nice_to_have = models.TextField(blank=True, help_text="Comma separated skills")
    required_education = models.CharField(max_length=120, blank=True, help_text="Optional minimum qualification")
    project_keywords = models.TextField(blank=True, help_text="Optional project evidence to look for")
    achievement_keywords = models.TextField(blank=True, help_text="Optional achievement evidence to look for")
    experience_years = models.PositiveSmallIntegerField(default=0)
    shortlist_size = models.PositiveSmallIntegerField(default=20)
    interview_date = models.DateTimeField(null=True, blank=True)
    interview_mode = models.CharField(max_length=120, default="Online · Google Meet")
    status = models.CharField(max_length=20, choices=[("open", "Open"), ("paused", "Paused"), ("closed", "Closed")], default="open")
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at"]
    def __str__(self): return self.title

class Candidate(models.Model):
    name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    location = models.CharField(max_length=120, blank=True)
    resume = models.FileField(upload_to="resumes/%Y/%m/", blank=True)
    resume_text = models.TextField(blank=True)
    education_profile = models.JSONField(default=list, blank=True)
    skills_profile = models.JSONField(default=list, blank=True)
    experience_profile = models.JSONField(default=list, blank=True)
    projects_profile = models.JSONField(default=list, blank=True)
    achievements_profile = models.JSONField(default=list, blank=True)
    certifications_profile = models.JSONField(default=list, blank=True)
    languages_profile = models.JSONField(default=list, blank=True)
    estimated_experience_years = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=80, default="Direct upload")
    stage = models.CharField(max_length=24, choices=[("new", "New"), ("shortlisted", "Shortlisted"), ("invited", "Invited"), ("interview", "Interview"), ("rejected", "Not selected")], default="new")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class ApplicationScore(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="scores")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="scores")
    score = models.PositiveSmallIntegerField(default=0)
    skills_score = models.PositiveSmallIntegerField(default=0)
    experience_score = models.PositiveSmallIntegerField(default=0)
    education_score = models.PositiveSmallIntegerField(default=0)
    projects_score = models.PositiveSmallIntegerField(default=0)
    achievements_score = models.PositiveSmallIntegerField(default=0)
    nlp_score = models.PositiveSmallIntegerField(default=0)
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    explanation = models.TextField(blank=True)
    shortlist_rank = models.PositiveSmallIntegerField(null=True, blank=True)
    scored_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = [("job", "candidate")]
        ordering = ["-score", "candidate__name"]

class Invitation(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="invitations")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="invitations")
    email_status = models.CharField(max_length=20, default="pending")
    sms_status = models.CharField(max_length=20, default="pending")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = [("job", "candidate")]
