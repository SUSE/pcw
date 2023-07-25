import os
import logging
from django.apps import AppConfig
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from pytz import utc

logger = logging.getLogger(__name__)
__SCHEDULER = None


def getScheduler():  # pylint: disable=invalid-name
    global __SCHEDULER
    if __SCHEDULER is None:
        logger.info("Create new BackgrounScheduler")
        executors = {
                'default': ThreadPoolExecutor(1),
            }
        job_defaults = {
                'coalesce': False,
                'max_instances': 1
            }
        __SCHEDULER = BackgroundScheduler(executors=executors, job_defaults=job_defaults, timezone=utc)
    return __SCHEDULER


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
