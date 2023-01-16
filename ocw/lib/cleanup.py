import logging
import traceback
from webui.settings import PCWConfig
from ocw.lib.azure import Azure
from ocw.lib.EC2 import EC2
from ocw.lib.gce import GCE
from ocw.lib.emailnotify import send_mail, send_cluster_notification
from ocw.apps import getScheduler

logger = logging.getLogger(__name__)


def cleanup_run():
    for namespace in PCWConfig.get_namespaces_for('cleanup'):
        try:
            providers = PCWConfig.get_providers_for('cleanup', namespace)
            logger.info("[%s] Run cleanup for %s", namespace, ','.join(providers))
            if 'azure' in providers:
                Azure(namespace).cleanup_all()

            if 'ec2' in providers:
                EC2(namespace).cleanup_all()

            if 'gce' in providers:
                GCE(namespace).cleanup_all()

        except Exception as ex:
            logger.exception("[%s] Cleanup failed!", namespace)
            send_mail('{} on Cleanup in [{}]'.format(type(ex).__name__, namespace), traceback.format_exc())


def list_clusters():
    for namespace in PCWConfig.get_namespaces_for('clusters'):
        try:
            clusters = EC2(namespace).all_clusters()
            quantity = sum(len(clusters[c1]) for c1 in clusters)
            logger.info("%d cluster(s) found", quantity)
            if quantity > 0:
                send_cluster_notification(namespace, clusters)
        except Exception as ex:
            logger.exception("[%s] List clusters failed!", namespace)
            send_mail('{} on List clusters in [{}]'.format(type(ex).__name__, namespace), traceback.format_exc())


def cleanup_k8s():
    for namespace in PCWConfig.get_namespaces_for('k8sclusters'):
        try:
            providers = PCWConfig.get_providers_for('k8sclusters', namespace)
            logger.debug("[%s] Run k8s cleanup for %s", namespace, ','.join(providers))

            if 'ec2' in providers:
                EC2(namespace).cleanup_k8s_jobs()

        except Exception as exception:
            logger.exception("[%s] k8s cleanup failed!", namespace)
            send_mail('{} on k8s cleanup in [{}]'.format(type(exception).__name__, namespace), traceback.format_exc())


def init_cron():
    getScheduler().add_job(cleanup_run, trigger='interval', minutes=60, id='cleanup_all', misfire_grace_time=1800)
    getScheduler().add_job(list_clusters, trigger='interval', hours=18, id='list_clusters', misfire_grace_time=10000)
    getScheduler().add_job(cleanup_k8s, trigger='interval', minutes=1440, id='cleanup_k8s_all',
                           misfire_grace_time=1800)
