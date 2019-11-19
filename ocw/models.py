from django.db import models
from enum import Enum
from datetime import timedelta


class ChoiceEnum(Enum):
    @classmethod
    def choices(cls):
        return [(i.name, i.value) for i in cls]

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return not self == other


class ProviderChoice(ChoiceEnum):
    GCE = 'Google'
    EC2 = 'EC2'
    AZURE = 'Azure'


class StateChoice(ChoiceEnum):
    UNK = 'unkown'
    ACTIVE = 'active'
    DELETING = 'deleting'
    DELETED = 'deleted'


class Instance(models.Model):

    provider = models.CharField(max_length=8, choices=ProviderChoice.choices())
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    age = models.DurationField(default=timedelta())
    active = models.BooleanField(default=False, help_text='True if the last sync found this instance on CSP')
    state = models.CharField(max_length=8, default=StateChoice.UNK, choices=StateChoice.choices(),
                             help_text='Local computed state of that Instance')
    instance_id = models.CharField(max_length=200, unique=True)
    region = models.CharField(max_length=64, default='')
    vault_namespace = models.CharField(max_length=64, default='')
    csp_info = models.TextField(default='')
    notified = models.BooleanField(default=False)

    def age_formated(self):
        days, remainder = divmod(self.age.total_seconds(), 60*60*24)
        hours, remainder = divmod(remainder, 60*60)
        minutes, seconds = divmod(remainder, 60)
        if days > 0:
            return '{:.0f}d{:.0f}h{:.0f}m'.format(days, hours, minutes)
        if hours > 0:
            return '{:.0f}h{:.0f}m'.format(hours, minutes)
        return '{:.0f}m'.format(minutes)

    class Meta:
        unique_together = (('provider', 'instance_id'),)
