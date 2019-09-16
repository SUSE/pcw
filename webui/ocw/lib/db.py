from webui.settings import ConfigFile
from ..models import Instance
from ..models import StateChoice
from ..models import ProviderChoice
from django.db import transaction
from django.utils import timezone
import json
import dateutil.parser
from threading import Thread
from threading import Lock
from .emailnotify import send_mail
import traceback
import logging
from .azure import Azure
from .EC2 import EC2
from .gce import GCE

update_thread = None
update_date = None
update_mutex = Lock()
logger = logging.getLogger(__name__)


@transaction.atomic
def sync_csp_to_local_db(pc_instances, provider, vault_namespace):
    t_now = timezone.now()
    o = Instance.objects
    o = o.filter(provider=provider, vault_namespace=vault_namespace)
    o = o.update(active=False)

    for i in pc_instances:
        if i.provider != provider:
            raise ValueError
        if i.vault_namespace != vault_namespace:
            raise ValueError

        logger.debug("Update/Create instance %s:%s @ %s\n\t%s", provider, i.instance_id, i.region, i.csp_info)
        if Instance.objects.filter(provider=i.provider, instance_id=i.instance_id).exists():
            o = Instance.objects.get(provider=i.provider, instance_id=i.instance_id)
            if o.region != i.region:
                logger.info("Instance %s:%s changed region from %s to %s", provider, i.instance_id, o.region, i.region)
                o.region = i.region
            if o.state == StateChoice.DELETED:
                logger.error("Update already DELETED instance %s:%s\n\t%s", provider, i.instance_id, i.csp_info)
            if o.state != StateChoice.DELETING:
                o.state = StateChoice.ACTIVE
        else:
            o = Instance(
                provider=provider,
                vault_namespace=vault_namespace,
                first_seen=i.first_seen,
                instance_id=i.instance_id,
                state=StateChoice.ACTIVE,
                region=i.region
            )
        o.csp_info = i.csp_info
        o.last_seen = t_now
        o.active = True
        o.age = o.last_seen - o.first_seen
        o.save()
    o = Instance.objects
    o = o.filter(provider=provider, active=False)
    o = o.update(state=StateChoice.DELETED)


def ec2_to_json(i):
    info = {
        'state': i.state['Name'],
        'image_id': i.image_id,
        'instance_lifecycle': i.instance_lifecycle,
        'instance_type': i.instance_type,
        'kernel_id': i.kernel_id,
        'launch_time': i.launch_time.isoformat(),
        'public_ip_address': i.public_ip_address,
        'security_groups': [sg['GroupName'] for sg in i.security_groups],
        'sriov_net_support': i.sriov_net_support,
        'tags': {t['Key']: t['Value'] for t in i.tags} if i.tags else {}
    }
    if i.state_reason:
        info['state_reason'] = i.state_reason['Message']

    if i.image:
        img = i.image
        info['image'] = {
            'image_id': img.image_id
        }
        # This happen, if the image was already deleted
        if img.meta.data is not None:
            info['image']['name'] = img.name

    return info


def ec2_to_local_instance(instance, vault_namespace, region):
    csp_info = ec2_to_json(instance)
    return Instance(
        provider=ProviderChoice.EC2,
        vault_namespace=vault_namespace,
        first_seen=dateutil.parser.parse(csp_info.get('launch_time', str(timezone.now()))),
        instance_id=instance.instance_id,
        state=StateChoice.ACTIVE,
        region=region,
        csp_info=json.dumps(csp_info, ensure_ascii=False)
    )


def azure_to_json(i):
    info = {
        'tags': i.tags,
        'name': i.name,
        'id': i.id,
        'type': i.type,
        'location': i.location
    }
    if (i.tags is not None and 'openqa_created_date' in i.tags):
        info['launch_time'] = i.tags.get('openqa_created_date')
    return info


def azure_to_local_instance(instance, vault_namespace):
    csp_info = azure_to_json(instance)
    return Instance(
        provider=ProviderChoice.AZURE,
        vault_namespace=vault_namespace,
        first_seen=dateutil.parser.parse(csp_info.get('launch_time', str(timezone.now()))),
        instance_id=instance.name,
        region=instance.location,
        csp_info=json.dumps(csp_info, ensure_ascii=False)
    )


def gce_to_json(i):
    info = {
        'tags': {m['key']: m['value'] for m in i['metadata']['items']} if 'items' in i['metadata'] else {},
        'name': i['name'],
        'id': i['id'],
        'machineType': GCE.url_to_name(i['machineType']),
        'zone': GCE.url_to_name(i['zone']),
        'status': i['status'],
        'launch_time': i['creationTimestamp'],
        'creation_time': i['creationTimestamp'],
    }
    if 'openqa_created_date' in info['tags']:
        info['launch_time'] = info['tags']['openqa_created_date']
    info['tags'].pop('sshKeys', '')
    return info


def gce_to_local_instance(instance, vault_namespace):
    csp_info = gce_to_json(instance)
    return Instance(
        provider=ProviderChoice.GCE,
        vault_namespace=vault_namespace,
        first_seen=dateutil.parser.parse(csp_info.get('launch_time', str(timezone.now()))),
        instance_id=instance['id'],
        region=GCE.url_to_name(instance['zone']),
        csp_info=json.dumps(csp_info, ensure_ascii=False)
    )


def __update_run():
    '''
    Each update is using Instance.active to mark the model is still availalbe on CSP.
    Instance.state is used to reflect the "local" state, e.g. if someone triggered a delete, the
    state will moved to DELETING. If the instance is gone from CSP, the state will set to DELETED.
    '''
    cfg = ConfigFile()
    global update_date, update_mutex
    for vault_namespace in cfg.getList(['vault', 'namespaces'], ['']):

        logger.info("Check vault_namespace: %s", vault_namespace)
        try:
            providers = cfg.getList(['vault.namespace.{}'.format(vault_namespace), 'providers'],
                                    ['ec2', 'azure', 'gce'])

            if 'azure' in providers:
                instances = Azure(vault_namespace).list_resource_groups()
                instances = [azure_to_local_instance(i, vault_namespace) for i in instances]
                logger.info("Got %d resources groups from Azure", len(instances))
                sync_csp_to_local_db(instances, ProviderChoice.AZURE, vault_namespace)

            if 'ec2' in providers:
                instances = []
                for region in cfg.getList(['ec2', 'regions'], EC2(vault_namespace).list_regions()):
                    instances_csp = EC2(vault_namespace).list_instances(region=region)
                    instances += [ec2_to_local_instance(i, vault_namespace, region) for i in instances_csp]
                    logger.info("Got %d instances from EC2 in region %s", len(instances), region)
                sync_csp_to_local_db(instances, ProviderChoice.EC2, vault_namespace)

            if 'gce' in providers:
                instances = GCE(vault_namespace).list_all_instances()
                instances = [gce_to_local_instance(i, vault_namespace) for i in instances]
                logger.info("Got %d instances from GCE", len(instances))
                sync_csp_to_local_db(instances, ProviderChoice.GCE, vault_namespace)

            with update_mutex:
                update_date = timezone.now()

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
