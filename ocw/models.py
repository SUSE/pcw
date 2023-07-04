import json
from datetime import datetime, timedelta, timezone
from django.db import models
from webui.PCWConfig import PCWConfig
from .enums import ProviderChoice, StateChoice


def format_seconds(seconds):
    days, remainder = divmod(seconds, 60*60*24)
    hours, remainder = divmod(remainder, 60*60)
    minutes, seconds = divmod(remainder, 60)
    if days > 0:
        return f'{days:.0f}d{hours:.0f}h{minutes:.0f}m'
    if hours > 0:
        return f'{hours:.0f}h{minutes:.0f}m'
    return f'{minutes:.0f}m'


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
    notified = models.BooleanField(default=False)
    ignore = models.BooleanField(default=False)
    TAG_IGNORE = 'pcw_ignore'

    def age_formated(self):
        return format_seconds(self.age.total_seconds())

    def ttl_formated(self):
        return format_seconds(self.ttl.total_seconds()) if (self.ttl) else ""

    def all_time_fields(self):
        all_time_pattern = "(age={}, first_seen={}, last_seen={}, ttl={})"
        first_fmt = 'None'
        last_fmt = 'None'
        if self.first_seen:
            first_fmt = self.first_seen.strftime('%Y-%m-%d %H:%M')
        if self.last_seen:
            last_fmt = self.last_seen.strftime('%Y-%m-%d %H:%M')
        return all_time_pattern.format(self.age_formated(), first_fmt, last_fmt, self.ttl_formated())

    def set_alive(self):
        self.last_seen = datetime.now(tz=timezone.utc)
        self.active = True
        self.age = self.last_seen - self.first_seen
        if self.state != StateChoice.DELETING:
            self.state = StateChoice.ACTIVE
        self.ignore = bool(self.cspinfo.get_tag(Instance.TAG_IGNORE))

    def get_type(self):
        return self.cspinfo.type

    class Meta:  # pylint: disable=too-few-public-methods
        unique_together = (('provider', 'instance_id', 'vault_namespace'),)


class CspInfo(models.Model):
    instance = models.OneToOneField(
        Instance,
        on_delete=models.CASCADE,
        primary_key=True,
    )
    tags = models.TextField(default='')
    type = models.CharField(max_length=200)

    def get_openqa_job_link(self):
        if self.get_tag('openqa_created_by') == 'openqa-suse-de' and self.get_tag('openqa_var_JOB_ID') is not None:
            url = f"{PCWConfig.get_feature_property('webui', 'openqa_url')}/t{self.get_tag('openqa_var_JOB_ID')}"
            title = self.get_tag('openqa_var_NAME', '')
            return {'url': url, 'title': title}
        return None

    def get_tag(self, tag_name, default_value=None):
        return json.loads(self.tags).get(tag_name, default_value)
