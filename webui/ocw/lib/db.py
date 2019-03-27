from ..models import Instance
from ..models import StateChoice
from django.db import transaction
from django.utils import timezone
import json
import dateutil.parser
from threading import Thread
from threading import Lock

update_thread = None
update_mutex = Lock()


@transaction.atomic
def update_or_create_instance(provider, instance_id, region, csp_info, active=True):
    t_now = timezone.now()

    if Instance.objects.filter(provider=provider, instance_id=instance_id).exists():
        o = Instance.objects.get(provider=provider, instance_id=instance_id)
        o.last_seen = t_now
        o.age = t_now - o.first_seen
        o.active = active
        o.csp_info = json.dumps(csp_info, ensure_ascii=False)
        if o.state == StateChoice.UNK:
            o.state = StateChoice.ACTIVE
        o.save()
    else:
        o = Instance(
                provider=provider,
                first_seen=dateutil.parser.parse(csp_info.get('launch_time', str(t_now))),
                last_seen=t_now,
                instance_id=instance_id,
                active=active,
                state=StateChoice.ACTIVE if active else StateChoice.DELETED,
                region=region,
                csp_info=json.dumps(csp_info, ensure_ascii=False)
                )
        o.age = o.last_seen - o.first_seen
        o.save()


def __update_run():
    # Avoid circular dependencies, so doing lazy import here
    from .azure import Azure
    from .EC2 import EC2
    from . import EC2db
    from . import azure

    azure.sync_instances_db(Azure().list_resource_groups())
    for region in EC2().list_regions():
        EC2db.sync_instances_db(region, EC2().list_instances(region=region))


def start_update():
    global update_thread, update_mutex

    update_mutex.acquire()
    if update_thread and update_thread.is_alive():
        update_mutex.release()
        return False

    update_thread = Thread(target=__update_run)
    update_thread.start()
    update_mutex.release()
    return True


def is_updating():
    global update_thread, update_mutex

    update_mutex.acquire()
    if update_thread and update_thread.is_alive():
        update_mutex.release()
        return True
    update_mutex.release()
    return False
