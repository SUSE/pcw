import logging
import traceback
from webui.PCWConfig import PCWConfig
from ocw.lib.azure import Azure
from ocw.lib.EC2 import EC2
from ocw.lib.gce import GCE
from ocw.lib.eks import EKS
from ocw.lib.emailnotify import send_mail, send_cluster_notification
from ocw.enums import ProviderChoice

logger = logging.getLogger(__name__)


def cleanup_run():
    for namespace in PCWConfig.get_namespaces_for('cleanup'):
        try:
            providers = PCWConfig.get_providers_for('cleanup', namespace)
            logger.info("[%s] Run cleanup for %s", namespace, ','.join(providers))
            if ProviderChoice.AZURE in providers:
                Azure(namespace).cleanup_all()

            if ProviderChoice.EC2 in providers:
                EC2(namespace).cleanup_all()

            if ProviderChoice.GCE in providers:
                GCE(namespace).cleanup_all()

        except Exception as ex:
            logger.exception("[%s] Cleanup failed!", namespace)
            send_mail('{} on Cleanup in [{}]'.format(type(ex).__name__, namespace), traceback.format_exc())


def list_clusters():
    for namespace in PCWConfig.get_namespaces_for('clusters'):
        try:
            clusters = EKS(namespace).all_clusters()
            quantity = sum(len(clusters[c1]) for c1 in clusters)
            logger.info("%d cluster(s) found", quantity)
            if quantity > 0:
                send_cluster_notification(namespace, clusters)
        except Exception as ex:
            logger.exception("[%s] List clusters failed!", namespace)
            send_mail('{} on List clusters in [{}]'.format(type(ex).__name__, namespace), traceback.format_exc())
