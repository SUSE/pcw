from django.core.management.base import BaseCommand
from webui.settings import PCWConfig
from ocw.lib.EC2 import EC2


class Command(BaseCommand):
    help = 'Delete all leftovers in all providers (according to pcw.ini)'

    def handle(self, *args, **options):
        for namespace in PCWConfig.get_namespaces_for('clusters'):
            EC2(namespace).delete_all_clusters()
