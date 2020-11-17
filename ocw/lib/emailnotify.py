from webui.settings import ConfigFile
from webui.settings import build_absolute_uri
from ..models import Instance
from datetime import timedelta
from texttable import Texttable
from django.urls import reverse
import json
import smtplib
import logging

logger = logging.getLogger(__name__)


def draw_instance_table(objects):

    from ocw import views
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
            build_absolute_uri(reverse(views.delete, args=[i.id]))
        ])
    return table.draw()


def send_leftover_notification():
    if not ConfigFile().has('notify'):
        return
    o = Instance.objects
    o = o.filter(active=True,
                 csp_info__icontains='openqa_created_by',
                 age__gt=timedelta(hours=int(ConfigFile().get('notify/age-hours', 12))))

    if o.filter(notified=False).count() == 0:
        return

    subject = ConfigFile().get('notify/subject', 'CSP left overs')
    body_prefix = "Message from {url}\n\n".format(url=build_absolute_uri())
    send_mail(subject, body_prefix + draw_instance_table(o))

    # Handle namespaces
    namespaces = list(dict.fromkeys([i.vault_namespace for i in o]))
    for namespace in namespaces:
        config_path = 'notify.namespace.{}/to'.format(namespace)
        if not ConfigFile().has(config_path):
            continue
        receiver_email = ConfigFile().get(config_path)
        namespace_objects = o.filter(vault_namespace=namespace)
        if namespace_objects.filter(notified=False).count() == 0:
            continue
        send_mail(subject, body_prefix + draw_instance_table(namespace_objects),
                  receiver_email=receiver_email)

    o.update(notified=True)


def send_cluster_notification(namespace, clusters):
    config_path = 'notify.cluster.namespace.{}/to'.format(namespace)
    if not ConfigFile().has('notify') or not ConfigFile().has(config_path):
        return
    if len(clusters):
        clusters_str = ' '.join([str(cluster) for cluster in clusters])
        logger.debug("Full clusters list - %s", clusters_str)
        send_mail("EC2 clusters found", clusters_str, receiver_email=ConfigFile().get(config_path))


def send_mail(subject, message, receiver_email=None):
    if not ConfigFile().has('notify'):
        return

    smtp_server = ConfigFile().get('notify/smtp')
    port = ConfigFile().get('notify/smtp-port', 25)
    sender_email = ConfigFile().get('notify/from')
    if receiver_email is None:
        receiver_email = ConfigFile().get('notify/to')
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
