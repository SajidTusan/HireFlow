import re
from datetime import date
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import ApplicationScore, Candidate, Invitation

_semantic_model = None
_semantic_model_checked = False

def extract_text(upload):
    """Read text PDFs normally and try OCR when a PDF has no text layer."""
    name = upload.name.lower()
    try:
        if name.endswith(".pdf"):
            page_text = []
            try:
                from pypdf import PdfReader
                upload.seek(0)
                page_text = [(page.extract_text() or "") for page in PdfReader(upload).pages]
            except Exception:
                pass
            missing_pages = [index for index, value in enumerate(page_text) if not value.strip()]
            if not page_text:
                missing_pages = None
            if missing_pages is not None and not missing_pages:
                return "\n".join(page_text)[:100_000]
            ocr_pages = _ocr_pdf(upload, missing_pages)
            if not page_text:
                page_text = [ocr_pages.get(index, "") for index in sorted(ocr_pages)]
            else:
                for index, value in ocr_pages.items():
                    if index < len(page_text) and not page_text[index].strip():
                        page_text[index] = value
            return "\n".join(page_text)[:100_000]
        if name.endswith(".docx"):
            from docx import Document
            document = Document(upload)
            return "\n".join(p.text for p in document.paragraphs)[:100_000]
        if name.endswith(".txt"):
            return upload.read().decode("utf-8", errors="ignore")[:100_000]
    except Exception:
        return ""
    return ""

def _ocr_pdf(upload, page_indexes=None):
    """OCR a bounded number of scanned PDF pages when Tesseract is installed."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
        if settings.TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        upload.seek(0)
        document = fitz.open(stream=upload.read(), filetype="pdf")
        pages = []
        selected = [(index, document[index]) for index in range(min(len(document), 15))] if page_indexes is None else [(index, document[index]) for index in page_indexes[:15] if index < len(document)]
        pages = {}
        for index, page in selected:
            pixmap = page.get_pixmap(dpi=180, colorspace=fitz.csRGB, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            pages[index] = pytesseract.image_to_string(image)
        document.close()
        return pages
    except Exception:
        # OCR is optional; if its Python packages or Tesseract executable are
        # missing, the upload view can report that no readable text was found.
        return ""

def _skills(raw):
    return [s.strip() for s in re.split(r"[,;\n]", raw or "") if s.strip()]

def _hybrid_relevance(job_context, candidate_context):
    """Use a cached local SBERT model when available, blended with TF-IDF.

    The first-use path is deliberately offline: missing model files fall back to
    TF-IDF instead of making a network request while a recruiter is scoring.
    """
    global _semantic_model, _semantic_model_checked
    tfidf_score = 0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vectors = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([job_context.casefold(), candidate_context.casefold()])
        tfidf_score = round(float(cosine_similarity(vectors[0:1], vectors[1:2])[0][0]) * 100)
    except (ImportError, ValueError):
        pass
    if not _semantic_model_checked:
        _semantic_model_checked = True
        try:
            from sentence_transformers import SentenceTransformer
            model_path = settings.SBERT_LOCAL_PATH or settings.SBERT_MODEL_NAME
            _semantic_model = SentenceTransformer(model_path, local_files_only=True)
        except Exception:
            _semantic_model = None
    if _semantic_model is None:
        return tfidf_score, "TF-IDF"
    try:
        from sentence_transformers.util import cos_sim
        vectors = _semantic_model.encode([job_context, candidate_context], convert_to_tensor=True, normalize_embeddings=True)
        semantic_score = max(0, min(100, round(float(cos_sim(vectors[0], vectors[1]).item()) * 100)))
        return round(semantic_score * .65 + tfidf_score * .35), "SBERT + TF-IDF"
    except Exception:
        return tfidf_score, "TF-IDF"

def candidate_summary(job, score):
    """Create a concise, evidence-based three-line recruiter summary."""
    candidate = score.candidate
    matched = ", ".join(score.matched_skills[:4]) or "no required skills detected yet"
    missing = ", ".join(score.missing_skills[:3]) or "no required skill gaps detected"
    years = candidate.estimated_experience_years
    project = candidate.project_records[0].get("name", "a listed project") if candidate.project_records else "no named project detected"
    return [
        f"{score.score}% overall match for {job.title}; strongest evidence: {matched}.",
        f"Experience estimate: {years} year(s); {score.nlp_score}% role-context relevance ({'SBERT + TF-IDF' if 'SBERT' in score.explanation else 'TF-IDF'}).",
        f"Review gaps: {missing}. Project evidence includes {project}.",
    ]

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

INSTITUTION_WORDS = re.compile(r"\b(university|college|institute|school|academy|polytechnic)\b", re.I)
YEAR_RANGE = re.compile(r"\b((?:19|20)\d{2})\s*(?:-|–|—|to)\s*((?:(?:19|20)\d{2})|present|current|now)\b", re.I)
URL_PATTERN = re.compile(r"https?://[^\s<>\])}]+", re.I)

def _clean_url(url):
    return url.rstrip(".,;:")

def _latest_year(text):
    ranges = YEAR_RANGE.findall(text or "")
    if ranges:
        end = ranges[-1][1]
        return date.today().year + 1 if end.casefold() in {"present", "current", "now"} else int(end)
    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", text or "")]
    return max(years, default=0)

def _education_records(lines):
    records = []
    for index, line in enumerate(lines):
        if not INSTITUTION_WORDS.search(line):
            continue
        nearby = " | ".join(lines[max(0, index - 1):min(len(lines), index + 2)])
        parts = [part.strip(" ,|·;-") for part in re.split(r"[|·;]", line) if part.strip(" ,|·;-")]
        institution = next((part for part in parts if INSTITUTION_WORDS.search(part)), line.strip())
        adjacent = [line, *lines[index + 1:index + 2], *lines[max(0, index - 1):index]]
        cgpa_match = next((match for part in adjacent if (match := re.search(r"\b(?:c?gpa|grade point average)\s*[:=\-]?\s*([0-9]+(?:\.[0-9]+)?(?:\s*/\s*[0-9]+(?:\.[0-9]+)?)?)", part, re.I))), None)
        degree_match = next((match for part in adjacent if (match := re.search(r"\b(Ph\.?D\.?|M\.?B\.?A\.?|M\.?Sc\.?|B\.?Sc\.?|B\.?A\.?|M\.?A\.?|Bachelor(?:'s)?(?: of [\w ]+)?|Master(?:'s)?(?: of [\w ]+)?|Diploma|Associate(?:'s)? degree)\b", part, re.I))), None)
        record = {"institution": institution[:180], "degree": degree_match.group(0)[:120] if degree_match else "", "cgpa": cgpa_match.group(1).replace(" ", "") if cgpa_match else "", "year": _latest_year(line) or _latest_year(nearby)}
        if not any(r["institution"].casefold() == record["institution"].casefold() for r in records):
            records.append(record)
    records.sort(key=lambda item: item["year"], reverse=True)
    return records[:2]

def _experience_records(lines):
    records = []
    role_words = re.compile(r"\b(engineer|developer|designer|manager|analyst|architect|consultant|specialist|lead|intern|officer|founder|coordinator|executive|scientist|administrator|director)\b", re.I)
    company_words = re.compile(r"\b(inc\.?|ltd\.?|limited|corp\.?|corporation|company|co\.?|llc|plc|technologies|solutions|systems|labs|group|studio)\b", re.I)
    for line in lines:
        cleaned = YEAR_RANGE.sub("", line).strip(" |·•,;-")
        rank = _latest_year(line)
        at_match = re.match(r"(.+?)\s+(?:at|@)\s+(.+)", cleaned, re.I)
        if at_match:
            role, company = at_match.group(1).strip(" -|·"), at_match.group(2).strip(" -|·")
        else:
            parts = [part.strip(" ,|·;-") for part in re.split(r"\s*(?:\||·|•|—|–)\s*", cleaned) if part.strip(" ,|·;- ")]
            if len(parts) >= 2:
                role, company = parts[0], parts[1]
                if (company_words.search(role) and role_words.search(company)) or (not role_words.search(role) and company_words.search(company) is None and role_words.search(company)):
                    role, company = company, role
            else:
                role, company = (parts[0], "") if parts else (cleaned, "")
        if not role and not company:
            continue
        records.append({"role": role[:180], "company": company[:180], "period": YEAR_RANGE.search(line).group(0) if YEAR_RANGE.search(line) else "", "year": rank, "details": line[:500]})
    records.sort(key=lambda item: item["year"], reverse=True)
    deduped = []
    seen = set()
    for record in records:
        key = (record["role"].casefold(), record["company"].casefold())
        if key not in seen:
            seen.add(key); deduped.append(record)
    return deduped[:8]

def _project_records(lines):
    records = []
    for line in lines:
        urls = [_clean_url(url) for url in URL_PATTERN.findall(line)]
        github = next((url for url in urls if "github.com/" in url.casefold()), "")
        cleaned = URL_PATTERN.sub("", line).strip(" |·•,:;-")
        parts = [part.strip(" |·•,:;-") for part in re.split(r"\s*(?:\||·|•|—|–)\s*", cleaned) if part.strip(" |·•,:;-")]
        name = parts[0] if parts else cleaned
        if name:
            records.append({"name": name[:180], "github_url": github, "details": line[:500], "year": _latest_year(line)})
    records.sort(key=lambda item: item["year"], reverse=True)
    return records[:10]

def _achievement_records(lines):
    records = []
    for line in lines:
        clean = line.strip(" •▪●*–-; ")
        if clean:
            records.append({"name": clean[:250], "year": _latest_year(clean)})
    records.sort(key=lambda item: item["year"], reverse=True)
    return records[:3]

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
    linkedin = next((_clean_url(url) for url in URL_PATTERN.findall(source) if "linkedin.com/in/" in url.casefold()), "")
    profile["linkedin_url"] = linkedin
    profile["education_records"] = _education_records(profile["education"])
    profile["experience_records"] = _experience_records(profile["experience"])
    profile["project_records"] = _project_records(profile["projects"])
    profile["latest_achievements"] = _achievement_records(profile["achievements"])
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

def refresh_candidate_profile(candidate, profile=None):
    profile = profile or extract_profile(candidate.resume_text)
    field_map = {
        **{f"{key}_profile": profile[key] for key in SECTION_NAMES},
        "education_records": profile["education_records"],
        "experience_records": profile["experience_records"],
        "project_records": profile["project_records"],
        "latest_achievements": profile["latest_achievements"],
        "linkedin_url": profile["linkedin_url"],
        "estimated_experience_years": profile["estimated_experience_years"],
    }
    for field, value in field_map.items():
        setattr(candidate, field, value)
    candidate.save(update_fields=list(field_map))
    return profile

def score_candidate(job, candidate):
    """Explainable resume parser and role match; does not infer protected traits."""
    text = (candidate.resume_text or "").casefold()
    profile = refresh_candidate_profile(candidate)
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
    job_context = " ".join([job.title, job.description, job.required_skills, job.nice_to_have, job.required_education, job.project_keywords, job.achievement_keywords])
    nlp_score, matching_method = _hybrid_relevance(job_context, evidence_text)
    experience_score = min(round(profile["estimated_experience_years"] / job.experience_years * 100), 100) if job.experience_years else 100
    required_education = job.required_education.casefold().strip()
    education_text = " ".join(candidate.education_profile).casefold()
    education_score = 100 if not required_education else (100 if required_education in education_text or any(level in education_text for level in _education_aliases(required_education)) else 0)
    project_terms, achievement_terms = _skills(job.project_keywords), _skills(job.achievement_keywords)
    project_text = " ".join(candidate.projects_profile).casefold()
    achievement_text = " ".join(candidate.achievements_profile).casefold()
    projects_score = round(sum(1 for term in project_terms if term.casefold() in project_text) / len(project_terms) * 100) if project_terms else 100
    achievements_score = round(sum(1 for term in achievement_terms if term.casefold() in achievement_text) / len(achievement_terms) * 100) if achievement_terms else 100
    weighted = [(skills_score, 35), (nlp_score, 25)]
    if job.experience_years: weighted.append((experience_score, 15))
    if job.required_education: weighted.append((education_score, 10))
    if project_terms: weighted.append((projects_score, 10))
    if achievement_terms: weighted.append((achievements_score, 5))
    score = round(sum(value * weight for value, weight in weighted) / sum(weight for _, weight in weighted))
    explanation_parts = [f"Skills {skills_score}%", f"{matching_method} role relevance {nlp_score}%"]
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
    calendar_line = f"\nCalendar link: {settings.INTERVIEW_CALENDAR_URL}" if settings.INTERVIEW_CALENDAR_URL else ""
    body = f"Hello {candidate.name},\n\nWe would like to invite you to interview for {job.title}.\nDate and time: {when}\nFormat: {job.interview_mode}{calendar_line}\n\nPlease reply to this email to confirm your availability.\n\nRegards,\nHiring team"
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
    if candidate.phone and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM:
        try:
            from twilio.rest import Client
            destination = candidate.phone if candidate.phone.startswith("whatsapp:") else f"whatsapp:{candidate.phone}"
            source = settings.TWILIO_WHATSAPP_FROM if settings.TWILIO_WHATSAPP_FROM.startswith("whatsapp:") else f"whatsapp:{settings.TWILIO_WHATSAPP_FROM}"
            Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN).messages.create(body=f"HireFlow: Interview invitation for {job.title}. {when}. Format: {job.interview_mode}. Please check your email to confirm.", from_=source, to=destination)
            invitation.whatsapp_status = "sent"
        except Exception:
            invitation.whatsapp_status = "failed"
    else:
        invitation.whatsapp_status = "not configured" if candidate.phone else "no number"
    invitation.sent_at = timezone.now()
    invitation.save()
    candidate.stage = "invited"
    candidate.save(update_fields=["stage"])
    return invitation
