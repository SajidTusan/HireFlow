from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import ApplicationScore, Candidate, Job
from .services import candidate_summary, extract_profile, extract_text, interview_questions, invite_candidate, refresh_candidate_profile, score_candidate

@login_required
def dashboard(request):
    jobs = Job.objects.annotate(applicant_count=Count("scores"))[:5]
    scores = ApplicationScore.objects.select_related("candidate", "job").order_by("-scored_at")[:6]
    return render(request, "recruiting/dashboard.html", {"jobs": jobs, "recent_scores": scores, "job_count": Job.objects.count(), "candidate_count": Candidate.objects.count(), "shortlisted_count": Candidate.objects.filter(stage="shortlisted").count(), "invite_count": Candidate.objects.filter(stage="invited").count()})

@login_required
def jobs(request):
    return render(request, "recruiting/jobs.html", {"jobs": Job.objects.annotate(applicant_count=Count("scores"))})

@login_required
def job_create(request):
    if request.method == "POST":
        job = Job(title=request.POST.get("title", "").strip(), department=request.POST.get("department", "").strip(), location=request.POST.get("location", "").strip(), description=request.POST.get("description", "").strip(), required_skills=request.POST.get("required_skills", "").strip(), nice_to_have=request.POST.get("nice_to_have", "").strip(), required_education=request.POST.get("required_education", "").strip(), project_keywords=request.POST.get("project_keywords", "").strip(), achievement_keywords=request.POST.get("achievement_keywords", "").strip(), experience_years=request.POST.get("experience_years") or 0, shortlist_size=request.POST.get("shortlist_size") or 20, interview_mode=request.POST.get("interview_mode", "Online · Google Meet").strip())
        if not job.title or not job.required_skills:
            messages.error(request, "Add a job title and at least one required skill.")
        else:
            job.save(); messages.success(request, "Role created. Upload resumes to start matching."); return redirect("job_detail", job_id=job.id)
    return render(request, "recruiting/job_form.html")

@login_required
def job_detail(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if request.method == "POST" and request.POST.get("action") == "rescore":
        for candidate in Candidate.objects.exclude(resume_text=""):
            score_candidate(job, candidate)
        messages.success(request, "Candidate scores refreshed against this role.")
        return redirect("job_detail", job_id=job.id)
    scores = job.scores.select_related("candidate").order_by("-score", "candidate__name")
    for item in scores:
        item.ai_summary = candidate_summary(job, item)
    return render(request, "recruiting/job_detail.html", {"job": job, "scores": scores, "applicant_count": scores.count(), "shortlisted_count": scores.filter(shortlist_rank__isnull=False).count(), "invited_count": job.invitations.count()})

@login_required
def shortlist(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if request.method == "POST":
        limit = max(1, min(500, int(request.POST.get("limit", job.shortlist_size) or job.shortlist_size)))
        job.shortlist_size = limit; job.save(update_fields=["shortlist_size"])
        scores = list(job.scores.order_by("-score", "candidate__name"))
        for score in scores:
            score.shortlist_rank = None; score.save(update_fields=["shortlist_rank"])
            if score.candidate.stage == "shortlisted": score.candidate.stage = "new"; score.candidate.save(update_fields=["stage"])
        for rank, score in enumerate(scores[:limit], 1):
            score.shortlist_rank = rank; score.save(update_fields=["shortlist_rank"])
            if score.candidate.stage == "new": score.candidate.stage = "shortlisted"; score.candidate.save(update_fields=["stage"])
        messages.success(request, f"Top {min(limit, len(scores))} candidates shortlisted.")
    return redirect("job_detail", job_id=job.id)

@login_required
def invite_shortlisted(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if request.method == "POST":
        scores = job.scores.filter(shortlist_rank__isnull=False).select_related("candidate")
        if not scores.exists():
            messages.warning(request, "Shortlist is empty. Rank candidates before sending invitations.")
        elif settings.CELERY_BROKER_URL:
            from .tasks import send_shortlist_invitations
            send_shortlist_invitations.delay(job.id)
            messages.success(request, "Invitation batch queued. Delivery statuses will update as the worker processes candidates.")
        else:
            sent = sum(1 for score in scores if invite_candidate(job, score.candidate))
            messages.success(request, f"Invitation workflow processed for {sent} shortlisted candidates. Check delivery status below.")
    return redirect("job_detail", job_id=job.id)

@login_required
def export_shortlist(request, job_id):
    import csv
    job = get_object_or_404(Job, pk=job_id)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="hireflow-{job.id}-shortlist.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Rank", "Candidate", "Email", "Phone", "Overall", "Skills score", "Experience score", "Education score", "Projects score", "Achievements score", "Role relevance", "Previous role", "Previous company", "Education 1 institute", "Education 1 degree", "Education 1 CGPA", "Education 2 institute", "Education 2 degree", "Education 2 CGPA", "Project names", "Project GitHub links", "LinkedIn URL", "Latest achievements", "Matched skills", "Missing skills"])
    for item in job.scores.filter(shortlist_rank__isnull=False).select_related("candidate").order_by("shortlist_rank"):
        candidate = item.candidate
        refresh_candidate_profile(candidate)
        role = candidate.experience_records[0] if candidate.experience_records else {}
        education_1 = candidate.education_records[0] if candidate.education_records else {}
        education_2 = candidate.education_records[1] if len(candidate.education_records) > 1 else {}
        writer.writerow([item.shortlist_rank, candidate.name, candidate.email, candidate.phone, item.score, item.skills_score, item.experience_score, item.education_score, item.projects_score, item.achievements_score, item.nlp_score, role.get("role", ""), role.get("company", ""), education_1.get("institution", ""), education_1.get("degree", ""), education_1.get("cgpa", ""), education_2.get("institution", ""), education_2.get("degree", ""), education_2.get("cgpa", ""), " | ".join(project.get("name", "") for project in candidate.project_records), " | ".join(f"{project.get('name', 'Project')}: {project.get('github_url', '')}" for project in candidate.project_records if project.get("github_url")), candidate.linkedin_url, " | ".join(entry.get("name", "") for entry in candidate.latest_achievements), ", ".join(item.matched_skills), ", ".join(item.missing_skills)])
    return response

@login_required
def candidates(request):
    qs = Candidate.objects.all().order_by("-created_at")
    q, stage = request.GET.get("q", "").strip(), request.GET.get("stage", "")
    if q: qs = qs.filter(name__icontains=q) | qs.filter(email__icontains=q)
    if stage: qs = qs.filter(stage=stage)
    return render(request, "recruiting/candidates.html", {"candidates": qs, "q": q, "stage": stage, "stage_choices": Candidate._meta.get_field("stage").choices})

@login_required
def candidate_upload(request):
    jobs = Job.objects.filter(status="open")
    if request.method == "POST":
        files = request.FILES.getlist("resumes")
        job = get_object_or_404(Job, pk=request.POST.get("job")) if request.POST.get("job") else None
        if not files:
            messages.error(request, "Choose one or more PDF, DOCX or TXT resumes.")
        else:
            added = 0
            for f in files:
                if f.size > 10 * 1024 * 1024 or not f.name.lower().endswith((".pdf", ".docx", ".txt")):
                    continue
                text = extract_text(f)
                if not text.strip(): continue
                f.seek(0)
                import re
                email = next(iter(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text)), "")
                phone = next(iter(re.findall(r"(?:\+?\d[\d\s().-]{7,}\d)", text)), "")
                name = next((line.strip() for line in text.splitlines() if line.strip()), f.name.rsplit(".", 1)[0])[:160]
                profile = extract_profile(text)
                candidate = Candidate.objects.create(name=name, email=email, phone=phone, resume=f, resume_text=text)
                refresh_candidate_profile(candidate, profile)
                if job: score_candidate(job, candidate)
                added += 1
            messages.success(request, f"{added} resume(s) parsed and added." if added else "No readable resume was found. Try text-based PDF, DOCX or TXT files.")
            return redirect("job_detail", job_id=job.id) if job else redirect("candidates")
    return render(request, "recruiting/upload.html", {"jobs": jobs})

@login_required
def candidate_detail(request, candidate_id):
    candidate = get_object_or_404(Candidate, pk=candidate_id)
    refresh_candidate_profile(candidate)
    scores = list(candidate.scores.select_related("job"))
    for score in scores:
        score.interview_questions = interview_questions(score.job, score)
    return render(request, "recruiting/candidate_detail.html", {"candidate": candidate, "scores": scores, "invitations": candidate.invitations.select_related("job")})

@login_required
def settings_page(request):
    import importlib.util
    import shutil
    from pathlib import Path
    from django.conf import settings
    tess_path = settings.TESSERACT_CMD
    tess_ready = Path(tess_path).is_file() if tess_path else bool(shutil.which("tesseract"))
    ocr_ready = tess_ready and all(importlib.util.find_spec(module) for module in ("fitz", "PIL", "pytesseract"))
    return render(request, "recruiting/settings.html", {"email_ready": bool(settings.EMAIL_HOST), "sms_ready": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_FROM_NUMBER), "whatsapp_ready": bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_WHATSAPP_FROM), "ocr_ready": ocr_ready})
