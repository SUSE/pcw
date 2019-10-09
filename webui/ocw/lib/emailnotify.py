from webui.settings import ConfigFile
from ..models import Instance
from datetime import timedelta
from texttable import Texttable
from django.urls import reverse
import json
import smtplib
import logging

logger = logging.getLogger(__name__)


def send_leftover_notification(request):
    from .. import views
    cfg = ConfigFile()
    if not cfg.has('notify'):
        return
    num_new = 0
    o = Instance.objects
    o = o.filter(active=True,
                 csp_info__icontains='openqa_created_by',
                 age__gt=timedelta(hours=int(cfg.get(['notify', 'age-hours'], 12))))

    table = Texttable(max_width=0)
    table.set_deco(Texttable.HEADER)
    table.header(['Provider', 'id', 'Created-By', 'Namespace', 'Age', 'Delete'])
    for i in o:
        if i.notified is False:
            num_new += 1
        j = json.loads(i.csp_info)
        hours, remainder = divmod(i.age.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        table.add_row([
            i.provider,
            i.instance_id,
            j['tags']['openqa_created_by'],
            i.vault_namespace,
            i.age_formated(),
            request.build_absolute_uri(reverse(views.delete, args=[i.id]))
        ])

    if num_new == 0:
        return

    subject = cfg.get(['notify', 'subject'], 'CSP left overs')
    body = '''\
Message from {url}


{table}
'''.format(table=table.draw(), url=request.build_absolute_uri('/'))
    send_mail(subject, body)
    o.update(notified=True)


def send_mail(subject, message):
    cfg = ConfigFile()
    if not cfg.has('notify'):
        return

    smtp_server = cfg.get(['notify', 'smtp'])
    port = cfg.get(['notify', 'smtp-port'], 25)
    sender_email = cfg.get(['notify', 'from'])
    receiver_email = cfg.get(['notify', 'to'])
    email = '''\
Subject: [Openqa-Cloud-Watch] {subject}
From: {_from}
To: {_to}

{message}
'''.format(subject=subject, _from=sender_email, _to=receiver_email, message=message)
    logger.info("Send Email To:'%s' Subject:'[Openqa-Cloud-Watch] %s'", receiver_email, subject)
    server = smtplib.SMTP(smtp_server, port)
    server.ehlo()
    server.sendmail(sender_email, receiver_email.split(','), email)
