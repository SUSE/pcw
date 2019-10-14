from webui.settings import ConfigFile
from ..models import Instance
from datetime import timedelta
from texttable import Texttable
from django.urls import reverse
import json
import smtplib
import logging

logger = logging.getLogger(__name__)


def draw_instance_table(request, objects):
    from .. import views

    table = Texttable(max_width=0)
    table.set_deco(Texttable.HEADER)
    table.header(['Provider', 'id', 'Created-By', 'Namespace', 'Age', 'Delete'])
    for i in objects:
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
    return table.draw()


def send_leftover_notification(request):
    cfg = ConfigFile()
    if not cfg.has('notify'):
        return
    o = Instance.objects
    o = o.filter(active=True,
                 csp_info__icontains='openqa_created_by',
                 age__gt=timedelta(hours=int(cfg.get(['notify', 'age-hours'], 12))))

    if o.filter(notified=True).count == 0:
        return

    subject = cfg.get(['notify', 'subject'], 'CSP left overs')
    body_prefix = "Message from {url}\n\n".format(url=request.build_absolute_uri('/'))
    send_mail(subject, body_prefix + draw_instance_table(request, o))
    o.update(notified=True)

    # Handle namespaces
    namespaces = list(dict.fromkeys([i.vault_namespace for i in o]))
    for namespace in namespaces:
        cfg_path = ['notify.namespace.{}'.format(namespace), 'to']
        if not cfg.has(cfg_path):
            continue
        receiver_email = cfg.get(cfg_path)
        namespace_objects = o.filter(vault_namespace=namespace)
        send_mail(subject, body_prefix + draw_instance_table(request, namespace_objects),
                  receiver_email=receiver_email)


def send_mail(subject, message, receiver_email=None):
    cfg = ConfigFile()
    if not cfg.has('notify'):
        return

    smtp_server = cfg.get(['notify', 'smtp'])
    port = cfg.get(['notify', 'smtp-port'], 25)
    sender_email = cfg.get(['notify', 'from'])
    if receiver_email is None:
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
