from django.db import transaction
from ..lib.vault import AzureCredential
from ..models import Instance
from ..models import ProviderChoice
from ..models import StateChoice
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from msrest.exceptions import AuthenticationError
from ..lib import db
import time


class Azure(AzureCredential):
    __instance = None
    __compute_mgmt_client = None
    __sp_credentials = None
    __resource_mgmt_client = None

    def __new__(cls):
        if Azure.__instance is None:
            Azure.__instance = object.__new__(cls)
            super(Azure, Azure.__instance).__init__()

        Azure.__instance.check_credentials()
        return Azure.__instance

    def __init__(self):
        pass

    def onExpired(self):
        self.revoke()
        self.__sp_credentials = None
        self.__compute_mgmt_client = None
        self.__resource_mgmt_client = None

    def subscription(self):
        return self.getData('subscription_id')

    def check_credentials(self):
        for i in range(1, 40):
            try:
                self.sp_credentials()
                return True
            except AuthenticationError as e:
                print('ServicePrincipalCredentials failed (attemp:{}) - {}'.format(i, str(e)))
                time.sleep(1)
        raise AuthenticationError("Invalid Azure credentials")

    def sp_credentials(self):
        if (self.__sp_credentials is None):
            self.__sp_credentials = ServicePrincipalCredentials(client_id=self.getData('client_id'),
                                                                secret=self.getData('client_secret'),
                                                                tenant=self.getData('tenant_id')
                                                                )
        return self.__sp_credentials

    def compute_mgmt_client(self):
        if (self.__compute_mgmt_client is None):
            self.__compute_mgmt_client = ComputeManagementClient(
                self.sp_credentials(), self.subscription())
        return self.__compute_mgmt_client

    def resource_mgmt_client(self):
        if (self.__resource_mgmt_client is None):
            self.__resoure_mgmt_client = ResourceManagementClient(
                self.sp_credentials(), self.subscription())
        return self.__resoure_mgmt_client

    def list_instances(self):
        return self.compute_mgmt_client().virtual_machines.list_all()

    def list_resource_groups(self):
        return self.resource_mgmt_client().resource_groups.list()

    def delete_resource(self, resource_id):
        return self.resource_mgmt_client().resource_groups.delete(resource_id)


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
