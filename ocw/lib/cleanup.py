import logging
import traceback
from webui.PCWConfig import PCWConfig
from ocw.lib.azure import Azure
from ocw.lib.ec2 import EC2
from ocw.lib.gce import GCE
from ocw.lib.emailnotify import send_mail
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
            send_mail(f'{type(ex).__name__} on Cleanup in [{namespace}]', traceback.format_exc())
