from datetime import timedelta
import smtplib
import logging
from email.mime.text import MIMEText
from texttable import Texttable
from django.urls import reverse
from webui.PCWConfig import PCWConfig
from webui.settings import build_absolute_uri
from ..models import Instance

logger = logging.getLogger(__name__)


def draw_instance_table(objects):

    from ocw import views
    table = Texttable(max_width=0)
    table.set_deco(Texttable.HEADER)
    table.header(['Provider', 'id', 'Created-By', 'Namespace', 'Age', 'Delete', 'openQA'])
    for obj in objects:
        link = obj.cspinfo.get_openqa_job_link()
        table.add_row([
            obj.provider,
            obj.instance_id,
            obj.cspinfo.get_tag('openqa_created_by', 'N/A'),
            obj.namespace,
            obj.age_formatted(),
            build_absolute_uri(reverse(views.delete, args=[obj.id])),
            "" if link is None else link['url']
        ])
    return table.draw()


def send_leftover_notification():
    if PCWConfig.has('notify'):
        all_instances = Instance.objects
        all_instances = all_instances.filter(active=True, age__gt=timedelta(hours=PCWConfig.get_feature_property(
            'notify', 'age-hours'))).exclude(ignore=True)
        body_prefix = f"Message from {build_absolute_uri()}\n\n"
        # Handle namespaces
        for namespace in PCWConfig.get_namespaces_for('notify'):
            receiver_email = PCWConfig.get_feature_property('notify', 'to', namespace)
            namespace_objects = all_instances.filter(namespace=namespace)
            if namespace_objects.filter(notified=False).count() > 0 and receiver_email:
                send_mail(f'CSP left overs - {namespace}',
                          body_prefix + draw_instance_table(namespace_objects), receiver_email=receiver_email)
        all_instances.update(notified=True)


def send_cluster_notification(namespace, clusters):
    if len(clusters) and PCWConfig.has('notify'):
        clusters_str = ''
        for region in clusters:
            clusters_list = ' '.join([str(cluster) for cluster in clusters[region]])
            clusters_str = f'{clusters_str}\n{region} : {clusters_list}'
        logger.debug("Full clusters list - %s", clusters_str)
        send_mail(f"[{namespace}] EC2 clusters found", clusters_str,
                  receiver_email=PCWConfig.get_feature_property('notify', 'to', namespace))


def send_mail(subject, message, receiver_email=None):
    if PCWConfig.has('notify'):
        smtp_server = PCWConfig.get_feature_property('notify', 'smtp')
        port = PCWConfig.get_feature_property('notify', 'smtp-port')
        sender_email = PCWConfig.get_feature_property('notify', 'from')
        if receiver_email is None:
            receiver_email = PCWConfig.get_feature_property('notify', 'to')
        mimetext = MIMEText(message)
        mimetext['Subject'] = f'[Openqa-Cloud-Watch] {subject}'
        mimetext['From'] = sender_email
        mimetext['To'] = receiver_email
        logger.debug("Send Email To:'%s' Subject:'[Openqa-Cloud-Watch] %s'", receiver_email, subject)
        server = smtplib.SMTP(smtp_server, port)
        server.ehlo()
        server.sendmail(sender_email, receiver_email.split(','), mimetext.as_string())
