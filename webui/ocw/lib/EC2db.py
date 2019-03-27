from django.db import transaction
from ..models import Instance
from ..models import ProviderChoice
from ..models import StateChoice
from ..lib import db


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

    return info


@transaction.atomic
def sync_instances_db(region, instances):
    o = Instance.objects
    o = o.filter(region=region, provider=ProviderChoice.EC2, state=StateChoice.ACTIVE)
    o = o.update(state=StateChoice.UNK, active=False)

    for i in instances:
        db.update_or_create_instance(
                provider=ProviderChoice.EC2,
                instance_id=i.instance_id,
                active=i.state['Name'] != 'terminated',
                region=region,
                csp_info=_instance_to_json(i))

    o = Instance.objects
    o = o.filter(region=region, provider=ProviderChoice.EC2, active=False)
    o = o.update(state=StateChoice.DELETED)
