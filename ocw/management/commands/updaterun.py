from django.core.management.base import BaseCommand
from ocw.lib.db import update_run


class Command(BaseCommand):
    help = 'Delete all leftovers in all providers (according to pcw.ini)'

    def handle(self, *args, **options):
        update_run()
