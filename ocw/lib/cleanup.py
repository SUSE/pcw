from webui.settings import ConfigFile
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
    cfg = ConfigFile()
    if cfg.has('cleanup'):
        for vault_namespace in cfg.getList(['cleanup', 'namespaces'], cfg.getList(['vault', 'namespaces'], [''])):
            try:
                providers = cfg.getList(['vault.namespace.{}'.format(vault_namespace), 'providers'],
                                        ['ec2', 'azure', 'gce'])
                logger.debug("[{}] Run cleanup for {}".format(vault_namespace, ','.join(providers)))
                if 'azure' in providers:
                    Azure(vault_namespace).cleanup_all()

                if 'ec2' in providers:
                    EC2(vault_namespace).cleanup_all()

                if 'gce' in providers:
                    GCE(vault_namespace).cleanup_all()

            except Exception as e:
                logger.exception("[{}] Cleanup failed!".format(vault_namespace))
                send_mail('{} on Cleanup in [{}]'.format(type(e).__name__, vault_namespace), traceback.format_exc())


def list_clusters():
    cfg = ConfigFile()
    if cfg.has('clusters'):
        for vault_namespace in cfg.getList(['clusters', 'namespaces'], ['']):
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
