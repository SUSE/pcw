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
    active = models.BooleanField(default=False)
    state = models.CharField(max_length=8, default=StateChoice.UNK, choices=StateChoice.choices())
    instance_id = models.CharField(max_length=200, unique=True)
    region = models.CharField(max_length=64, default='')
    csp_info = models.TextField(default='')

    class Meta:
        unique_together = (('provider', 'instance_id'),)
