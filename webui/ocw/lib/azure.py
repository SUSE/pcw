from django.db import transaction
from ..lib.vault import AzureCredential
from ..models import Instance
from ..models import ProviderChoice
from ..models import StateChoice
from ..lib import db


class Azure:
    __instance = None
    __credentials = None

    def __new__(cls):
        if Azure.__instance is None:
            Azure.__instance = object.__new__(cls)
            Azure.__instance.__credentials = AzureCredential()
        return Azure.__instance

    def list_instances(self):
        return self.__credentials.compute_mgmt_client().virtual_machines.list_all()

    def list_resource_groups(self):
        return self.__credentials.resource_mgmt_client().resource_groups.list()

    def delete_resource(self, resource_id):
        return self.__credentials.resource_mgmt_client().resource_groups.delete(resource_id)


def _instance_to_json(i):
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


@transaction.atomic
def sync_instances_db(instances):
    o = Instance.objects
    o = o.filter(provider=ProviderChoice.AZURE, state=StateChoice.ACTIVE)
    o = o.update(active=False, state=StateChoice.UNK)

    for i in instances:
        db.update_or_create_instance(
                provider=ProviderChoice.AZURE,
                instance_id=i.name,
                active=True,
                region=i.location,
                csp_info=_instance_to_json(i))

    o = Instance.objects
    o = o.filter(provider=ProviderChoice.AZURE, active=False)
    o = o.update(state=StateChoice.DELETED)
