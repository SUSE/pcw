from django.apps import AppConfig
import os
import logging

logger = logging.getLogger(__name__)


class OcwConfig(AppConfig):
    name = 'ocw'
    ready_called = False

    def ready(self):
        if os.environ.get('RUN_MAIN', None) != 'true' or self.ready_called:
            return
        self.ready_called = True

        try:
            import ocw.lib.db
            import ocw.lib.cleanup

            ocw.lib.db.init_cron()
            ocw.lib.cleanup.init_cron()
        except Exception:
            logger.exception("Failure on initialize cronjobs")
