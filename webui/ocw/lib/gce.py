from .vault import GCECredential
from ..models import Instance
from ..models import ProviderChoice
from ..models import StateChoice
from django.db import transaction
from ..lib import db


class GCE:
    __instance = None
    __credentials = None

    def __new__(cls):
        if GCE.__instance is None:
            GCE.__instance = object.__new__(cls)
            GCE.__instance.__credentials = GCECredential()
        return GCE.__instance

    def list_instances(self, zone='europe-west1-b'):
        return self.__credentials.list_instances(zone)


def _instance_to_json(i):
    info = {
            'tags': {m['key']: m['value'] for m in i['metadata']['items']} if i['metadata']['items'] else {},
            'name': i['name'],
            'id': i['id'],
            'machineType': i['machineType']
          }
    if 'openqa_created_date' in info['tags']:
        info['launch_time'] = info['tags']['openqa_created_date']
    return info


@transaction.atomic
def sync_instances_db(instances):
    o = Instance.objects
    o = o.filter(provider=ProviderChoice.GCE, state=StateChoice.ACTIVE)
    o = o.update(active=False, state=StateChoice.UNK)

    for i in instances:
        db.update_or_create_instance(
                provider=ProviderChoice.GCE,
                instance_id=i['id'],
                active=True,
                region='UNKNOWN',
                csp_info=_instance_to_json(i))

    o = Instance.objects
    o = o.filter(provider=ProviderChoice.GCE, active=False)
    o = o.update(state=StateChoice.DELETED)
