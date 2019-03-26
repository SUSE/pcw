from django.db import models
from enum import Enum
from datetime import timedelta


class ProviderChoice(Enum):
    GCE = 'Google'
    EC2 = 'EC2'
    AZURE = 'Azure'


class Instance(models.Model):

    provider = models.CharField(max_length=8, choices=[(str(tag), tag.value) for tag in ProviderChoice])
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    age = models.DurationField(default=timedelta())
    active = models.BooleanField(default=False)
    instance_id = models.CharField(max_length=200, unique=True)
    region = models.CharField(max_length=64, default='')
    csp_info = models.TextField(default='')

    class Meta:
        unique_together = (('provider', 'instance_id'),)
