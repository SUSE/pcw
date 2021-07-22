from django.core.management.base import BaseCommand
from webui.settings import PCWConfig
from ocw.lib.EC2 import EC2
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Key pairs cleanup for EC2. Attention! It will deleting **ALL** keys which starting from openqa-'

    def handle(self, *args, **options):
        for namespace in PCWConfig.get_namespaces_for('cleanup'):
            try:
                logger.debug("[{}] Run keypair cleanup for ec2".format(namespace))
                EC2(namespace).cleanup_keys()

            except Exception:
                logger.exception("[{}] Key pair cleanup failed!".format(namespace))
