from django.core.management.base import BaseCommand
from recruiting.models import Candidate, Job
from recruiting.services import score_candidate

class Command(BaseCommand):
    help = "Create fictional candidate and job records for a local HireFlow demo."
    def handle(self, *args, **options):
        job, _ = Job.objects.get_or_create(title="Product-minded Django Developer", defaults={"department": "Engineering", "location": "Dhaka · Hybrid", "description": "Build thoughtful tools that help teams work better.", "required_skills": "Python, Django, PostgreSQL, REST API", "nice_to_have": "Docker, AWS, React", "required_education": "Bachelor's degree", "project_keywords": "payment system, analytics dashboard", "achievement_keywords": "reduced API response time, impact award", "experience_years": 3, "shortlist_size": 5, "interview_mode": "Online · Google Meet"})
        job.required_education = "Bachelor's degree"
        job.project_keywords = "payment system, analytics dashboard"
        job.achievement_keywords = "reduced API response time, impact award"
        job.save(update_fields=["required_education", "project_keywords", "achievement_keywords"])
        first_names = ["Ayesha", "Rafi", "Nabila", "Tanvir", "Mehjabin", "Samiul", "Farzana", "Imran", "Nusrat", "Arif", "Jannat", "Sakib", "Maliha", "Reza", "Tania", "Anik", "Samira", "Fahim", "Priya", "Zubair"]
        last_names = ["Rahman", "Hasan", "Chowdhury", "Ahmed", "Karim", "Islam", "Hossain", "Khan", "Akter", "Sarker"]
        skill_sets = ["Python, Django, PostgreSQL, REST API, Docker, AWS", "Python, Django, PostgreSQL, REST API, React", "Python, Django, REST API", "Python, PostgreSQL, REST API, Docker", "Python, Django, PostgreSQL, REST API, AWS", "Django, PostgreSQL, Docker, React", "Python, Django, PostgreSQL, REST API, Docker", "Python, Django, PostgreSQL"]
        made = 0
        for i, name in enumerate(first_names):
            full_name = f"{name} {last_names[i % len(last_names)]}"
            resume_text = f"{full_name}\nSoftware engineer with {i % 7 + 1} years of experience.\n\nEDUCATION\nBachelor of Science in Computer Science · Example University · 2018–2022\n\nWORK EXPERIENCE\nSoftware Engineer · Example Labs · 2022–Present\nBuilt scalable services and collaborated with product teams.\n\nPROJECTS\nPayment system and analytics dashboard for a high-volume marketplace.\n\nACHIEVEMENTS\nReduced API response time by 40%; recognized with team impact award.\n\nCERTIFICATIONS\nCloud fundamentals\n\nLANGUAGES\nBangla, English\n\nSKILLS\n{skill_sets[i % len(skill_sets)]}."
            candidate, created = Candidate.objects.get_or_create(email=f"{name.lower()}.{i+1}@example.com", defaults={"name": full_name, "phone": f"+880170000{i+1:04d}", "location": "Dhaka", "source": "Demo data", "resume_text": resume_text})
            if created: made += 1
            elif candidate.source == "Demo data":
                candidate.resume_text = resume_text
                candidate.save(update_fields=["resume_text"])
            score_candidate(job, candidate)
        self.stdout.write(self.style.SUCCESS(f"Demo role ready with {job.scores.count()} ranked candidate profiles ({made} newly created)."))
