import json
import logging
from datetime import datetime, timedelta, timezone
from django.db import models
from .enums import ProviderChoice, StateChoice
from .lib.openqa import OpenQA, get_url, OpenQAClientError


def format_seconds(seconds):
    if not seconds:
        return "0s"
    days, remainder = divmod(seconds, 60*60*24)
    hours, remainder = divmod(remainder, 60*60)
    minutes, seconds = divmod(remainder, 60)
    return "".join([
        f"{days:.0f}d" if days > 0 else "",
        f"{hours:.0f}h" if hours > 0 else "",
        f"{minutes:.0f}m" if minutes > 0 else "",
        f"{seconds:.0f}s" if seconds > 0 else "",
    ])


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

    def age_formatted(self):
        return format_seconds(self.age.total_seconds())

    def ttl_formatted(self):
        return format_seconds(self.ttl.total_seconds())

    def ttl_expired(self):
        return self.age.total_seconds() > self.ttl.total_seconds()

    def all_time_fields(self):
        all_time_pattern = "(age={}, first_seen={}, last_seen={}, ttl={})"
        first_fmt = 'None'
        last_fmt = 'None'
        if self.first_seen:
            first_fmt = self.first_seen.strftime('%Y-%m-%d %H:%M')
        if self.last_seen:
            last_fmt = self.last_seen.strftime('%Y-%m-%d %H:%M')
        return all_time_pattern.format(self.age_formatted(), first_fmt, last_fmt, self.ttl_formatted())

    def set_alive(self):
        self.last_seen = datetime.now(tz=timezone.utc)
        self.active = True
        self.age = self.last_seen - self.first_seen
        if self.state != StateChoice.DELETING:
            self.state = StateChoice.ACTIVE
        self.ignore = bool(self.cspinfo.get_tag(Instance.TAG_IGNORE))

    def get_type(self):
        return self.cspinfo.type

    def is_cancelled(self) -> bool:
        job = self.cspinfo.get_tag("openqa_var_job_id")
        server = self.cspinfo.get_tag("openqa_var_server")
        if job and server:
            try:
                return OpenQA(
                    server=server,
                    retries=1,  # default is 5
                    wait=5,     # default is 10
                ).is_cancelled(job)
            except OpenQAClientError as exc:
                logging.warning("%s: %s", server, exc)
        return False

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
        server = self.get_tag('openqa_var_server')
        if server:
            try:
                server = get_url(server)
            except OpenQAClientError as exc:
                logging.warning("%s: %s", server, exc)
                return None
            job_id = self.get_tag('openqa_var_job_id')
            if job_id:
                url = f"{server}/t{job_id}"
                title = self.get_tag('openqa_var_name', '')
                return {'url': url, 'title': title}
        return None

    def get_tag(self, tag_name, default_value=None):
        return json.loads(self.tags).get(tag_name, default_value)
