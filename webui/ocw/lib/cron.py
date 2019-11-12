from threading import Thread
from threading import Lock
from time import sleep
from datetime import timedelta, datetime, timezone
import logging

logger = logging.getLogger(__name__)


class CronJob:
    def __init__(self, name, func, interval=timedelta(hours=1), arg=None):
        self.__name = name
        self.__func = func
        self.__interval = interval
        self.__arg = arg
        self.__last_start = None
        self.__last_stop = None

    def run(self):
        if not self.__last_start or self.__last_start + self.__interval < datetime.now(timezone.utc):
            self.__running = True
            self.__last_start = datetime.now(timezone.utc)
            self.__last_stop = None
            logger.debug("Run cron job '{}'".format(self.__name))
            try:
                self.__func(self.__arg)
            except Exception:
                logger.exception("Cron job '{}' failed".format(self.__name))
            self.__last_stop = datetime.now(timezone.utc)
            self.__running = False

    def name(self): return self.__name
    def lastStart(self): return self.__last_start
    def lastStop(self): return self.__last_stop
    def isRunning(self): return self.__running
    def forceRun(self): self.__last_start = None


def cron_run():
    while CronLoop().running():
        sleep(1)
        CronLoop().triggerJobs()


class CronLoop:
    __instance = None

    def __new__(cls):
        if not CronLoop.__instance:
            CronLoop.__instance = self = object.__new__(cls)
            self.__thread_mutex = Lock()
            self.__list_mutex = Lock()
            self.__running = False
            self.__thread = None
            self.__cron_jobs = dict()
            self.__start()

        return CronLoop.__instance

    def __start(self):
        with self.__thread_mutex:
            if self.__thread and self.__thread.is_alive():
                return False

            self.__running = True
            self.__thread = Thread(target=cron_run)
            self.__thread.start()
        return True

    def running(self):
        with self.__thread_mutex:
            return self.__running

    def stop(self):
        with self.__thread_mutex:
            if self.__thread and self.__thread.is_alive():
                return False
            self.__running = False
        self.__thread.join()
        return True

    def addJob(self, job):
        with self.__list_mutex:
            if job.name() in self.__cron_jobs:
                raise ValueError("Cron with name '{}' already registerd".format(job.name()))
            logger.info("Add cron with name '{}'".format(job.name()))
            self.__cron_jobs[job.name()] = job

    def findJob(self, name):
        with self.__list_mutex:
            if name not in self.__cron_jobs:
                raise KeyError("Cron with name '{}' isn't registered".format(name))
            return self.__cron_jobs[name]

    def triggerJobs(self):
        copy_list = None
        with self.__list_mutex:
            copy_list = self.__cron_jobs
        for job in copy_list:
            copy_list[job].run()
