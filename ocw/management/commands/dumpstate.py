from django.core.management.base import BaseCommand
from ocw.lib.dump_state import dump_state


class Command(BaseCommand):
    help = 'Dump current state (amount of all entities \
        tracked by pcw) of all providers (according to pcw.ini)'

    def handle(self, *args, **options):
        dump_state()
