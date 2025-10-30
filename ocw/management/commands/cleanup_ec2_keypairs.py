from django.core.management.base import BaseCommand
from webui.PCWConfig import PCWConfig
from ocw.lib.ec2 import EC2


class Command(BaseCommand):
    help = 'Delete all leftovers in all providers (according to pcw.ini)'

    def handle(self, *args, **options):
        for namespace in PCWConfig.get_namespaces_for('cleanup'):
            EC2(namespace).cleanup_keypairs()
