from django.db import models
from enum import Enum
from datetime import timedelta
from webui.settings import PCWConfig
import json


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


def format_seconds(seconds):
    days, remainder = divmod(seconds, 60*60*24)
    hours, remainder = divmod(remainder, 60*60)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return '{:.0f}d{:.0f}h{:.0f}m'.format(days, hours, minutes)
    if hours > 0:
        return '{:.0f}h{:.0f}m'.format(hours, minutes)
    return '{:.0f}m'.format(minutes)


class Instance(models.Model):
    provider = models.CharField(max_length=8, choices=ProviderChoice.choices())
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    age = models.DurationField(default=timedelta())
    ttl = models.DurationField(default=timedelta(0))
    active = models.BooleanField(default=False, help_text='True if the last sync found this instance on CSP')
    state = models.CharField(max_length=8, default=StateChoice.UNK, choices=StateChoice.choices(),
                             help_text='Local computed state of that Instance')
    instance_id = models.CharField(max_length=200)
    region = models.CharField(max_length=64, default='')
    vault_namespace = models.CharField(max_length=64, default='')
    csp_info = models.TextField(default='')
    notified = models.BooleanField(default=False)

    def age_formated(self):
        return format_seconds(self.age.total_seconds())

    def ttl_formated(self):
        return format_seconds(self.ttl.total_seconds()) if(self.ttl) else ""

    def all_time_fields(self):
        all_time_pattern = "(age={}, first_seen={}, last_seen={}, ttl={})"
        first_fmt = self.first_seen.strftime('%Y-%m-%d %H:%M')
        last_fmt = self.last_seen.strftime('%Y-%m-%d %H:%M')
        return all_time_pattern.format(self.age_formated(), first_fmt, last_fmt, self.ttl_formated())

    def tags(self):
        try:
            info = json.loads(self.csp_info)
            if 'tags' in info:
                return info['tags']
        except json.JSONDecodeError:
            pass
        return dict()

    def get_openqa_job_link(self):
        tags = self.tags()
        if tags.get('openqa_created_by', '') == 'openqa-suse-de' and 'openqa_var_JOB_ID' in tags:
            url = '{}/t{}'.format(PCWConfig.get_feature_property('webui', 'openqa_url'), tags['openqa_var_JOB_ID'])
            title = tags.get('openqa_var_NAME', '')
            return {'url': url, 'title': title}
        return None

    class Meta:
        unique_together = (('provider', 'instance_id', 'vault_namespace'),)
