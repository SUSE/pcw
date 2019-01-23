from django.db import transaction
from django.utils import timezone
from ec2.models import Instance
import json


def _instance_to_json(i):
    # TODO find a generic way from boto3 object to json
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
            'tags': i.tags,
            }
    if i.state_reason:
        info['state_reason'] = i.state_reason['Message']

    if i.image:
        img = i.image
        info['image'] = {
                'image_id': img.image_id,
                'name': img.name,
                }

    return json.dumps(info, ensure_ascii=False)


@transaction.atomic
def sync_instances_db(region, instances):
    t_now = timezone.now()
    Instance.objects.filter(region=region).update(active=False)

    for i in instances:
        active = i.state['Name'] != 'terminated'
        if Instance.objects.filter(instance_id=i.instance_id).exists():
            o = Instance.objects.get(instance_id=i.instance_id)
            o.last_seen = t_now
            o.active = active
            o.csp_info = _instance_to_json(i)
            o.save()
        else:
            o = Instance(
                    first_seen=t_now,
                    last_seen=t_now,
                    instance_id=i.instance_id,
                    active=active,
                    region=region,
                    csp_info=_instance_to_json(i),
                    )
            o.save()
