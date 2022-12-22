from django.core.management.base import BaseCommand
from ocw.lib.cleanup import cleanup_k8s


class Command(BaseCommand):
    help = 'Delete all leftovers in all kubernetes clusters for all providers (according to pcw.ini)'

    def handle(self, *args, **options):
        cleanup_k8s()
