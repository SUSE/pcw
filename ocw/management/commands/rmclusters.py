from django.core.management.base import BaseCommand
from webui.PCWConfig import PCWConfig
from ocw.lib.eks import EKS


class Command(BaseCommand):
    help = 'Delete all leftovers in all providers (according to pcw.ini)'

    def handle(self, *args, **options):
        for namespace in PCWConfig.get_namespaces_for('clusters'):
            EKS(namespace).delete_all_clusters()
