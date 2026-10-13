# HireFlow

HireFlow is a Django hiring workspace for resume intake, explainable role matching, configurable top-N shortlists, and interview invitation delivery by email and SMS.

## What's inside

- Create roles with required and preferred skills, experience signal, interview format, and shortlist size.
- Upload multiple PDF, DOCX, or TXT resumes. The app extracts text and looks for email/phone contact details.
- Export shortlist CSVs with the latest role and company, the two most recent education institutions and CGPAs, project names and GitHub links, LinkedIn URL, and latest achievements.
- Match candidates to a role using exact skill evidence, optional offline Sentence-BERT semantic embeddings blended with TF-IDF, and explainable experience/education/project/achievement dimensions.
- Parse common CV sections into education, employment history, projects, achievements, certifications, and languages. Estimate experience from stated years and work date ranges.
- Add optional education, project, and achievement criteria to a role. Candidate profiles show per-dimension scores and criteria that were not configured are marked as such.
- Prepare role-specific interview questions from missing skills and project evidence, and export a ranked shortlist with score dimensions as CSV.
- Shortlist the highest-ranked N candidates, with N configurable per role.
- Process interview invitations for the shortlist. Email uses Django email; SMS can use Twilio. Delivery status is recorded for each channel.
- Dashboard, role pipeline, candidate profiles, search and stage filters, Django admin, and responsive modern UI.

The matching engine deliberately ignores age, gender, photos, and other protected traits. The role review screen provides a live top-N slider, blind-name toggle, side-by-side candidate comparison, fit-dimension radar chart, and three-line evidence summary. Scores are a review aid; the recruiter should inspect resumes before making hiring decisions. Resume extraction recognizes common headings (for example, “Education”, “Work Experience”, “Projects”, and “Achievements”); unusual headings may need manual review. It identifies education institutions/degree/CGPA, role/company pairs, GitHub/LinkedIn URLs, project names, and recent achievements when those appear in readable text. Experience is an estimate from stated years or date ranges. Text-based PDFs work directly. Scanned/image-only PDFs use OCR if Tesseract is installed and `TESSERACT_CMD` is configured when needed; OCR processes at most 15 pages per resume. Equivalent skills written differently may not match.

## Run locally (Windows PowerShell)

```powershell
cd "D:\Sajid\Django Project\HireFlow"
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Put the generated value in `.env` as `DJANGO_SECRET_KEY=...`, then initialize and start the app:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_data
python manage.py runserver
```

Open <http://127.0.0.1:8000/> and sign in with the administrator account. The demo dataset includes a role and fictional ranked candidates. The `.env` file is ignored by Git.

For scanned PDFs, install Tesseract OCR on the computer and set `TESSERACT_CMD` in `.env` to the `tesseract.exe` path if it is not on `PATH`. Then install Python dependencies with `pip install -r requirements.txt` and restart the server. The Settings page shows whether OCR is ready.

## Email and SMS

Without SMTP credentials, invitation emails print to the Django runserver console. For live email, configure `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL` in `.env`.

For live SMS, set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`. Candidate mobile numbers should be stored in international format such as `+8801...`. For WhatsApp, configure `TWILIO_WHATSAPP_FROM` with your approved WhatsApp sender (or sandbox sender). Candidates must opt in; the Settings page shows whether delivery providers are configured.

On a role page, choose a shortlist size and click **Shortlist top N**. Review contacts, the candidate score breakdown, interview questions, and interview format, then export the shortlist if needed. Click **Send interview invitations** when ready. The app records the result of each email and SMS channel. Configure provider credentials before sending to real candidates.

## Before production

Set a private `DJANGO_SECRET_KEY`, set `DJANGO_DEBUG=0`, configure `DJANGO_ALLOWED_HOSTS`, use PostgreSQL and durable private resume storage, enforce HTTPS, and add backups, retention controls, and role-based recruiter access. Restrict resume uploads and keep real candidate data out of demo environments. For WhatsApp, obtain candidate opt-in and use a Twilio-approved sender/template; follow applicable messaging rules.

## Semantic matching and background invitations

HireFlow combines transparent skill/dimension scoring with TF-IDF. If the `all-MiniLM-L6-v2` Sentence-Transformers model is already cached locally, the role-context score blends SBERT semantic similarity (65%) and TF-IDF (35%). Scoring does not download a model automatically; set `SBERT_LOCAL_PATH` to a local model directory in `.env` to enable offline semantic embeddings. Without the model, TF-IDF remains active.

The role review page includes a live top-N shortlist preview, bias-conscious blind-name mode, side-by-side candidate comparison, a skills/experience/education/projects/achievements radar, and evidence-based three-line summaries. The blind toggle affects the review screen only; access control should be configured before using real applicant data.

Invitations run synchronously by default for a simple local setup. For a background worker, run Redis locally, set `CELERY_BROKER_URL=redis://127.0.0.1:6379/0` in `.env`, then start the web app and a worker in separate PowerShell terminals:

```powershell
python manage.py runserver
celery -A hireflow worker --pool=solo --loglevel=info
```

Set `INTERVIEW_CALENDAR_URL` in `.env` to append a scheduling/calendar link to invitation emails. Email variables include candidate name, role, interview date/time, interview format, and the configured calendar link.
