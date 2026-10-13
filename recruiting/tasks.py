from celery import shared_task
from django.shortcuts import get_object_or_404

from .models import Job
from .services import invite_candidate


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def send_shortlist_invitations(self, job_id):
    """Send the selected role's invitation batch from a Celery worker."""
    job = get_object_or_404(Job, pk=job_id)
    sent = 0
    for score in job.scores.filter(shortlist_rank__isnull=False).select_related("candidate"):
        invite_candidate(job, score.candidate)
        sent += 1
    return {"job_id": job_id, "processed": sent}
