from webui.settings import ConfigFile
from ..models import Instance
from ..models import StateChoice
from django.db import transaction
from django.utils import timezone
import json
import dateutil.parser
from threading import Thread
from threading import Lock
from datetime import datetime
from .emailnotify import send_mail
import traceback
import logging

update_thread = None
update_date = None
update_mutex = Lock()
logger = logging.getLogger(__name__)


@transaction.atomic
def update_or_create_instance(provider, instance_id, region, csp_info, vault_namespace):
    t_now = timezone.now()
    logger.debug("Update/Create instance %s:%s @ %s\n\t%s", provider, instance_id, region, csp_info)
    if Instance.objects.filter(provider=provider, instance_id=instance_id).exists():
        o = Instance.objects.get(provider=provider, instance_id=instance_id)
        o.last_seen = t_now
        o.age = t_now - o.first_seen
        o.active = True
        o.csp_info = json.dumps(csp_info, ensure_ascii=False)
        if o.region != region:
            logger.info("Instance %s:%s changed region from %s to %s", provider, instance_id, o.region, region)
            o.region = region
        if o.state == StateChoice.DELETED:
            logger.error("Update already DELETED instance %s:%s\n\t%s", provider, instance_id, csp_info)
        if o.state != StateChoice.DELETING:
            o.state = StateChoice.ACTIVE
        o.save()
    else:
        o = Instance(
            provider=provider,
            vault_namespace=vault_namespace,
            first_seen=dateutil.parser.parse(csp_info.get('launch_time', str(t_now))),
            last_seen=t_now,
            instance_id=instance_id,
            active=True,
            state=StateChoice.ACTIVE,
            region=region,
            csp_info=json.dumps(csp_info, ensure_ascii=False)
        )
        o.age = o.last_seen - o.first_seen
        o.save()


def __update_run():
    # Avoid circular dependencies, so doing lazy import here
    from .azure import Azure
    from .EC2 import EC2
    from .gce import GCE
    from . import EC2db
    from . import azure
    from . import gce
    global update_date, update_mutex
    cfg = ConfigFile()

    '''
    Each update is using Instance.active to mark the model is still availalbe on CSP.
    Instance.state is used to reflect the "local" state, e.g. if someone triggered a delete, the
    state will moved to DELETING. If the instance is gone from CSP, the state will set to DELETED.
    '''
    for vault_namespace in cfg.getList(['vault', 'namespaces'], ['']):

        logger.info("Check vault_namespace: %s", vault_namespace)
        try:
            providers = cfg.getList(['vault.namespace.{}'.format(vault_namespace), 'providers'],
                                    ['ec2', 'azure', 'gce'])

            if 'azure' in providers:
                instances = Azure(vault_namespace).list_resource_groups()
                logger.info("Got %d resources groups from Azure", len(instances))
                azure.sync_instances_db(instances, vault_namespace)

            if 'ec2' in providers:
                for region in cfg.getList(['ec2', 'regions'], EC2(vault_namespace).list_regions()):
                    instances = EC2(vault_namespace).list_instances(region=region)
                    logger.info("Got %d instances from EC2 in region %s", len(instances), region)
                    EC2db.sync_instances_db(region, instances, vault_namespace)

            if 'gce' in providers:
                instances = GCE(vault_namespace).list_all_instances()
                logger.info("Got %d instances from GCE", len(instances))
                gce.sync_instances_db(instances, vault_namespace)

            with update_mutex:
                update_date = datetime.now(timezone.utc)

        except Exception as e:
            logger.exception("Update failed!")
            send_mail(type(e).__name__ + ' on Update', traceback.format_exc())


def start_update():
    global update_thread, update_mutex

    with update_mutex:
        if update_thread and update_thread.is_alive():
            return False

        update_thread = Thread(target=__update_run)
        update_thread.start()
    return True


def is_updating():
    global update_thread, update_mutex
    with update_mutex:
        return update_thread and update_thread.is_alive()


def last_update():
    global update_mutex
    with update_mutex:
        return update_date.isoformat() if update_date is not None else ''
