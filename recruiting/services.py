import re
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import ApplicationScore, Candidate, Invitation

def extract_text(upload):
    """Extract readable text from PDF, DOCX or plain text files."""
    name = upload.name.lower()
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(upload)
            return "\n".join(page.extract_text() or "" for page in reader.pages)[:100_000]
        if name.endswith(".docx"):
            from docx import Document
            document = Document(upload)
            return "\n".join(p.text for p in document.paragraphs)[:100_000]
        if name.endswith(".txt"):
            return upload.read().decode("utf-8", errors="ignore")[:100_000]
    except Exception:
        return ""
    return ""

def _skills(raw):
    return [s.strip() for s in re.split(r"[,;\n]", raw or "") if s.strip()]

SECTION_NAMES = {
    "skills": {"skills", "technical skills", "core skills", "key skills", "competencies"},
    "education": {"education", "education history", "academic background", "academic history", "qualifications"},
    "experience": {"experience", "work experience", "employment history", "professional experience", "work history", "career history"},
    "projects": {"projects", "project experience", "selected projects", "key projects", "personal projects"},
    "achievements": {"achievements", "awards", "accomplishments", "honors", "honours", "recognition"},
    "certifications": {"certifications", "certificates", "licenses", "licences", "courses"},
    "languages": {"languages", "language proficiency"},
}
SECTION_LOOKUP = {name: key for key, names in SECTION_NAMES.items() for name in names}

def extract_profile(text):
    """Split common resume sections and estimate stated years of experience."""
    profile = {key: [] for key in SECTION_NAMES}
    current = None
    for raw_line in (text or "").splitlines():
        line = re.sub(r"^[\s•▪●*\-–]+", "", raw_line).strip()
        if not line:
            continue
        first, separator, remainder = line.partition(":")
        heading = re.sub(r"[:\s]+$", "", first if separator else line).casefold().strip()
        if heading in SECTION_LOOKUP and len(first) < 65:
            current = SECTION_LOOKUP[heading]
            if separator and remainder.strip():
                profile[current].append(remainder.strip()[:500])
            continue
        if current and len(profile[current]) < 30:
            profile[current].append(line[:500])
    source = text or ""
    matches = [int(value) for value in re.findall(r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", source, flags=re.I)]
    year = date.today().year
    for start, end in re.findall(r"\b((?:19|20)\d{2})\s*(?:-|–|—|to)\s*((?:(?:19|20)\d{2})|present|current|now)\b", source, flags=re.I):
        finish = year if end.casefold() in {"present", "current", "now"} else int(end)
        if finish >= int(start):
            matches.append(min(finish - int(start), 50))
    profile["estimated_experience_years"] = max(matches, default=0)
    return profile

def interview_questions(job, score):
    questions = []
    for skill in score.missing_skills[:2]:
        questions.append(f"Could you share a recent example of using {skill} to solve a real problem?")
    for skill in score.matched_skills[:1]:
        questions.append(f"How did you apply {skill} in a project, and what trade-offs did you make?")
    for keyword in _skills(job.project_keywords)[:1]:
        if keyword.casefold() not in " ".join(score.matched_skills).casefold():
            questions.append(f"Which project best demonstrates your experience with {keyword}?")
    if not questions:
        questions.append(f"Which achievement from your recent work are you most proud of, and how did you measure its impact?")
    return questions[:4]

def score_candidate(job, candidate):
    """Explainable resume parser and role match; does not infer protected traits."""
    text = (candidate.resume_text or "").casefold()
    profile = extract_profile(candidate.resume_text)
    for key in SECTION_NAMES:
        setattr(candidate, f"{key}_profile", profile[key])
    candidate.estimated_experience_years = profile["estimated_experience_years"]
    candidate.save(update_fields=[*(f"{key}_profile" for key in SECTION_NAMES), "estimated_experience_years"])
    evidence_text = " ".join(candidate.skills_profile + candidate.experience_profile + candidate.projects_profile + candidate.achievements_profile + candidate.certifications_profile).casefold()
    required, preferred = _skills(job.required_skills), _skills(job.nice_to_have)
    def contains(skill):
        return re.search(r"(?<!\w)" + re.escape(skill.casefold()) + r"(?!\w)", evidence_text) is not None
    matched = [s for s in required if contains(s)]
    missing = [s for s in required if s not in matched]
    preferred_matched = [s for s in preferred if contains(s)]
    required_pct = len(matched) / len(required) if required else 0
    preferred_pct = len(preferred_matched) / len(preferred) if preferred else 0
    if required and preferred:
        skills_score = round(required_pct * 80 + preferred_pct * 20)
    elif required:
        skills_score = round(required_pct * 100)
    elif preferred:
        skills_score = round(preferred_pct * 100)
    else:
        skills_score = 100
    job_context = " ".join([job.title, job.required_skills, job.nice_to_have, job.project_keywords, job.achievement_keywords])
    nlp_score = 0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vectors = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([job_context.casefold(), evidence_text])
        nlp_score = round(float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0]) * 100)
    except (ImportError, ValueError):
        # Keep the app usable in a minimal install; exact skill matching still works.
        nlp_score = 0
    experience_score = min(round(profile["estimated_experience_years"] / job.experience_years * 100), 100) if job.experience_years else 100
    required_education = job.required_education.casefold().strip()
    education_text = " ".join(candidate.education_profile).casefold()
    education_score = 100 if not required_education else (100 if required_education in education_text or any(level in education_text for level in _education_aliases(required_education)) else 0)
    project_terms, achievement_terms = _skills(job.project_keywords), _skills(job.achievement_keywords)
    project_text = " ".join(candidate.projects_profile).casefold()
    achievement_text = " ".join(candidate.achievements_profile).casefold()
    projects_score = round(sum(1 for term in project_terms if term.casefold() in project_text) / len(project_terms) * 100) if project_terms else 100
    achievements_score = round(sum(1 for term in achievement_terms if term.casefold() in achievement_text) / len(achievement_terms) * 100) if achievement_terms else 100
    weighted = [(skills_score, 40), (nlp_score, 5)]
    if job.experience_years: weighted.append((experience_score, 25))
    if job.required_education: weighted.append((education_score, 10))
    if project_terms: weighted.append((projects_score, 15))
    if achievement_terms: weighted.append((achievements_score, 5))
    score = round(sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted))
    explanation_parts = [f"Skills {skills_score}%", f"TF-IDF role relevance {nlp_score}%"]
    if job.experience_years: explanation_parts.append(f"Experience {experience_score}% ({candidate.estimated_experience_years} years detected)")
    if job.required_education: explanation_parts.append(f"Education {education_score}%")
    if project_terms: explanation_parts.append(f"Projects {projects_score}%")
    if achievement_terms: explanation_parts.append(f"Achievements {achievements_score}%")
    explanation = "; ".join(explanation_parts) + "."
    return ApplicationScore.objects.update_or_create(job=job, candidate=candidate, defaults={"score": score, "skills_score": skills_score, "experience_score": experience_score, "education_score": education_score, "projects_score": projects_score, "achievements_score": achievements_score, "nlp_score": nlp_score, "matched_skills": matched + preferred_matched, "missing_skills": missing, "explanation": explanation})[0]

def _education_aliases(required):
    aliases = {"bachelor": ("bachelor", "b.sc", "bsc", "bachelor of"), "master": ("master", "m.sc", "msc", "mba"), "phd": ("phd", "doctorate", "doctoral"), "diploma": ("diploma",)}
    return next((values for key, values in aliases.items() if key in required), (required,))

def invite_candidate(job, candidate):
    invitation, _ = Invitation.objects.get_or_create(job=job, candidate=candidate)
    when = timezone.localtime(job.interview_date).strftime("%d %b %Y, %I:%M %p") if job.interview_date else "We will share the available interview times shortly"
    subject = f"Interview invitation · {job.title}"
    body = f"Hello {candidate.name},\n\nWe would like to invite you to interview for {job.title}.\nDate and time: {when}\nFormat: {job.interview_mode}\n\nPlease reply to this email to confirm your availability.\n\nRegards,\nHiring team"
    if candidate.email:
        try:
            sent = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [candidate.email], fail_silently=False)
            invitation.email_status = "sent" if sent else "failed"
        except Exception:
            invitation.email_status = "failed"
    else:
        invitation.email_status = "no address"
    if candidate.phone and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER:
        try:
            from twilio.rest import Client
            Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN).messages.create(body=f"HireFlow: Interview invitation for {job.title}. {when}. Format: {job.interview_mode}. Please check your email to confirm.", from_=settings.TWILIO_FROM_NUMBER, to=candidate.phone)
            invitation.sms_status = "sent"
        except Exception:
            invitation.sms_status = "failed"
    else:
        invitation.sms_status = "not configured" if candidate.phone else "no number"
    invitation.sent_at = timezone.now()
    invitation.save()
    candidate.stage = "invited"
    candidate.save(update_fields=["stage"])
    return invitation
