from ..models import Instance
from django.db import transaction
from django.utils import timezone
import json
import dateutil.parser


@transaction.atomic
def update_or_create_instance(provider, instance_id, active, region, csp_info):
    t_now = timezone.now()

    if Instance.objects.filter(provider=provider, instance_id=instance_id).exists():
        o = Instance.objects.get(provider=provider, instance_id=instance_id)
        o.last_seen = t_now
        o.age = t_now - o.first_seen
        o.active = active
        o.csp_info = json.dumps(csp_info, ensure_ascii=False)
        o.save()
    else:
        o = Instance(
                provider=provider,
                first_seen=dateutil.parser.parse(csp_info.get('launch_time', str(t_now))),
                last_seen=t_now,
                instance_id=instance_id,
                active=active,
                region=region,
                csp_info=json.dumps(csp_info, ensure_ascii=False)
                )
        o.age = o.last_seen - o.first_seen
        o.save()
