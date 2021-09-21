from webui.settings import PCWConfig
from webui.settings import build_absolute_uri
from ..models import Instance
from datetime import timedelta
from texttable import Texttable
from django.urls import reverse
import json
import smtplib
import logging
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def draw_instance_table(objects):

    from ocw import views
    table = Texttable(max_width=0)
    table.set_deco(Texttable.HEADER)
    table.header(['Provider', 'id', 'Created-By', 'Namespace', 'Age', 'Delete', 'openQA'])
    for i in objects:
        j = json.loads(i.csp_info)
        hours, remainder = divmod(i.age.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        link = i.get_openqa_job_link()
        table.add_row([
            i.provider,
            i.instance_id,
            j['tags']['openqa_created_by'],
            i.vault_namespace,
            i.age_formated(),
            build_absolute_uri(reverse(views.delete, args=[i.id])),
            "" if link is None else link['url']
        ])
    return table.draw()


def send_leftover_notification():
    if PCWConfig.has('notify'):
        o = Instance.objects
        o = o.filter(active=True, csp_info__icontains='openqa_created_by',
                     age__gt=timedelta(hours=PCWConfig.get_feature_property('notify', 'age-hours')))
        body_prefix = "Message from {url}\n\n".format(url=build_absolute_uri())
        # Handle namespaces
        for namespace in PCWConfig.get_namespaces_for('notify'):
            receiver_email = PCWConfig.get_feature_property('notify', 'to', namespace)
            namespace_objects = o.filter(vault_namespace=namespace)
            if namespace_objects.filter(notified=False).count() > 0 and receiver_email:
                send_mail('CSP left overs - {}'.format(namespace),
                          body_prefix + draw_instance_table(namespace_objects), receiver_email=receiver_email)
        o.update(notified=True)


def send_cluster_notification(namespace, clusters):
    if len(clusters) and PCWConfig.has('notify'):
        clusters_str = ' '.join([str(cluster) for cluster in clusters])
        logger.debug("Full clusters list - %s", clusters_str)
        send_mail("EC2 clusters found", clusters_str,
                  receiver_email=PCWConfig.get_feature_property('cluster.notify', 'to', namespace))


def send_mail(subject, message, receiver_email=None):
    if PCWConfig.has('notify'):
        smtp_server = PCWConfig.get_feature_property('notify', 'smtp')
        port = PCWConfig.get_feature_property('notify', 'smtp-port')
        sender_email = PCWConfig.get_feature_property('notify', 'from')
        if receiver_email is None:
            receiver_email = PCWConfig.get_feature_property('notify', 'to')
        mimetext = MIMEText(message)
        mimetext['Subject'] = '[Openqa-Cloud-Watch] {}'.format(subject)
        mimetext['From'] = sender_email
        mimetext['To'] = receiver_email
        logger.info("Send Email To:'%s' Subject:'[Openqa-Cloud-Watch] %s'", receiver_email, subject)
        server = smtplib.SMTP(smtp_server, port)
        server.ehlo()
        server.sendmail(sender_email, receiver_email.split(','), mimetext.as_string())
