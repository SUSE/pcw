from webui.settings import ConfigFile
from ocw.lib.azure import Azure
from ocw.lib.EC2 import EC2
from ocw.lib.gce import GCE
from ocw.lib.emailnotify import send_mail
from ocw.lib.cron import CronLoop, CronJob
from datetime import timedelta
import logging
import traceback

logger = logging.getLogger(__name__)


def cleanup_run(arg):
    cfg = ConfigFile()
    for vault_namespace in cfg.getList(['vault', 'namespaces'], ['']):
        try:
            providers = cfg.getList(['vault.namespace.{}'.format(vault_namespace), 'providers'],
                                    ['ec2', 'azure', 'gce'])
            if 'azure' in providers:
                Azure(vault_namespace).cleanup_all()

            if 'ec2' in providers:
                EC2(vault_namespace).cleanup_all()

            if 'gce' in providers:
                GCE(vault_namespace).cleanup_all()

        except Exception as e:
            logger.exception("Cleanup failed!")
            send_mail(type(e).__name__ + ' on Cleanup', traceback.format_exc())


def init_cron():
    CronLoop().addJob(CronJob('cleanup_all', cleanup_run, timedelta(hours=1)))
