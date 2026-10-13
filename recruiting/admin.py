from django.contrib import admin
from .models import Job, Candidate, ApplicationScore, Invitation
admin.site.register([Job, Candidate, ApplicationScore, Invitation])
