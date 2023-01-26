from datetime import datetime
from datetime import timedelta
from datetime import timezone
import logging
import json
import subprocess
from pathlib import Path
from webui.settings import PCWConfig


class Provider:

    def __init__(self, namespace: str):
        self._namespace = namespace
        self.dry_run = PCWConfig.getBoolean('default/dry_run')
        self.logger = logging.getLogger(self.__module__)
        self.auth_json = self.read_auth_json()

    def read_auth_json(self):
        authcachepath = Path('/var/pcw/{}/{}.json'.format(self._namespace, self.__class__.__name__))
        if authcachepath.exists():
            with authcachepath.open(encoding="utf-8") as file_handle:
                return json.loads(file_handle.read())
        else:
            self.log_err('Credentials not found in {}. Terminating', authcachepath)
            raise FileNotFoundError('Credentials not found')

    def get_data(self, name=None) -> str:
        if name is None:
            return self.auth_json
        return self.auth_json[name]

    def is_outdated(self, timestamp):
        """
            is_outdated - calculates if certain resource bypass maximum allowed TTL
            maximum allowed TTL is controled by cleanup/max-age-hours pcw.ini config param
            :param timestamp: usually creation time of resource or any other timestamp which may be used to identify
                age of the resource
            :return: True if resource is already too old , false otherwise
        """
        delta_in_hours = PCWConfig.get_feature_property('cleanup', 'max-age-hours', self._namespace)
        max_allowed_age = datetime.now(timezone.utc) - timedelta(hours=delta_in_hours)
        return max_allowed_age > timestamp

    def log_info(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.info("[%s] %s", self._namespace, message)

    def log_warn(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.warning("[%s] %s", self._namespace, message)

    def log_err(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.error("[%s] %s", self._namespace, message)

    def log_dbg(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.debug("[%s] %s", self._namespace, message)

    def cmd_exec(self, cmd):
        return subprocess.call(cmd.split())
