from django.apps import AppConfig
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from pytz import utc

logger = logging.getLogger(__name__)
__scheduler = None


def getScheduler():
    global __scheduler
    if __scheduler is None:
        logger.info("Create new BackgrounScheduler")
        executors = {
                'default': ThreadPoolExecutor(1),
            }
        job_defaults = {
                'coalesce': False,
                'max_instances': 1
            }
        __scheduler = BackgroundScheduler(executors=executors, job_defaults=job_defaults, timezone=utc)
    return __scheduler


class OcwConfig(AppConfig):
    name = 'ocw'
    ready_called = False

    def ready(self):
        if os.environ.get('RUN_MAIN', None) != 'true' or self.ready_called:
            return
        self.ready_called = True

        getScheduler().start()

        try:
            import ocw.lib.db

            ocw.lib.db.init_cron()
        except Exception:
            logger.exception("Failure on initialize cronjobs")
