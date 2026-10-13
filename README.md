# HireFlow

HireFlow is a Django hiring workspace for resume intake, explainable role matching, configurable top-N shortlists, and interview invitation delivery by email and SMS.

## What's inside

- Create roles with required and preferred skills, experience signal, interview format, and shortlist size.
- Upload multiple PDF, DOCX, or TXT resumes. The app extracts text and looks for email/phone contact details.
- Match candidates to a role using an explainable skill phrase and experience baseline. Every match shows the skills found, missing skills, and scoring explanation.
- Parse common CV sections into education, employment history, projects, achievements, certifications, and languages. Estimate experience from stated years and work date ranges.
- Add optional education, project, and achievement criteria to a role. Candidate profiles show per-dimension scores and criteria that were not configured are marked as such.
- Prepare role-specific interview questions from missing skills and project evidence, and export a ranked shortlist with score dimensions as CSV.
- Shortlist the highest-ranked N candidates, with N configurable per role.
- Process interview invitations for the shortlist. Email uses Django email; SMS can use Twilio. Delivery status is recorded for each channel.
- Dashboard, role pipeline, candidate profiles, search and stage filters, Django admin, and responsive modern UI.

The matching baseline is deliberately transparent and does not use age, gender, photos, or other protected traits. It combines exact skill phrase coverage, TF-IDF cosine similarity between the role and resume text, and optional evidence for experience, education, projects, and achievements. Active criteria are normalized into an overall score and shown separately in each candidate profile. Resume section extraction recognizes common headings (for example, “Education”, “Work Experience”, “Projects”, and “Achievements”); unusual headings may need manual review. Experience is an estimate from stated years or date ranges. Image-only/scanned resumes need OCR, and equivalent skills written differently may not match. Treat scores as a review aid; the recruiter should review each shortlist.

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

## Email and SMS

Without SMTP credentials, invitation emails print to the Django runserver console. For live email, configure `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS`, and `DEFAULT_FROM_EMAIL` in `.env`.

For live SMS, set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM_NUMBER`. Candidate mobile numbers should be stored in international format such as `+8801...`. The Settings page shows whether delivery providers are configured.

On a role page, choose a shortlist size and click **Shortlist top N**. Review contacts, the candidate score breakdown, interview questions, and interview format, then export the shortlist if needed. Click **Send interview invitations** when ready. The app records the result of each email and SMS channel. Configure provider credentials before sending to real candidates.

## Before production

Set a private `DJANGO_SECRET_KEY`, set `DJANGO_DEBUG=0`, configure `DJANGO_ALLOWED_HOSTS`, use PostgreSQL and durable private resume storage, enforce HTTPS, and add backups, retention controls, role-based recruiter access, and an async delivery queue such as Celery. Restrict resume uploads and keep real candidate data out of demo environments.
