from webui.settings import ConfigFile, PCWConfig
from ocw.lib.azure import Azure
from ocw.lib.EC2 import EC2
from ocw.lib.gce import GCE
from ocw.lib.emailnotify import send_mail
from ocw.lib.emailnotify import send_cluster_notification
import logging
import traceback
from ocw.apps import getScheduler

logger = logging.getLogger(__name__)


def cleanup_run():
    if ConfigFile().has('cleanup'):
        for namespace in PCWConfig.get_namespaces_for('cleanup', fallback_to_default=True):
            try:
                providers = PCWConfig.get_providers_for('cleanup', namespace)
                logger.debug("[{}] Run cleanup for {}".format(namespace, ','.join(providers)))
                if 'azure' in providers:
                    Azure(namespace).cleanup_all()

                if 'ec2' in providers:
                    EC2(namespace).cleanup_all()

                if 'gce' in providers:
                    GCE(namespace).cleanup_all()

            except Exception as e:
                logger.exception("[{}] Cleanup failed!".format(namespace))
                send_mail('{} on Cleanup in [{}]'.format(type(e).__name__, namespace), traceback.format_exc())


def list_clusters():
    if ConfigFile().has('clusters'):
        for vault_namespace in PCWConfig.get_namespaces_for('clusters'):
            try:
                clusters = EC2(vault_namespace).all_clusters()
                logger.info("%d clusters found", len(clusters))
                send_cluster_notification(vault_namespace, clusters)
            except Exception as e:
                logger.exception("[{}] List clusters failed!".format(vault_namespace))
                send_mail('{} on List clusters in [{}]'.format(
                    type(e).__name__, vault_namespace), traceback.format_exc())


def init_cron():
    getScheduler().add_job(cleanup_run, trigger='interval', minutes=60, id='cleanup_all')
    getScheduler().add_job(list_clusters, trigger='interval', hours=18, id='list_clusters')
