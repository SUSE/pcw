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
import logging


class Azure:
    __instance = None
    __credentials = None
    __compute_mgmt_client = None
    __sp_credentials = None
    __resource_mgmt_client = None
    __logger = None

    def __new__(cls):
        if Azure.__instance is None:
            Azure.__instance = object.__new__(cls)
            Azure.__instance.__credentials = AzureCredential()
            Azure.__instance.__logger = logging.getLogger(__name__)

        Azure.__instance.check_credentials()
        return Azure.__instance

    def subscription(self):
        return self.__credentials.getData('subscription_id')

    def check_credentials(self):
        if self.__credentials.isExpired():
            self.__sp_credentials = None
            self.__credentials.renew()

        for i in range(1, 40):
            try:
                self.sp_credentials()
                return True
            except AuthenticationError:
                self.__logger.info("check_credentials failed (attemp:%d) - for client_id %s should expire at %s",
                                   i, self.__credentials.getData('client_id'), self.__credentials.auth_expire)
                time.sleep(1)
        raise AuthenticationError("Invalid Azure credentials")

    def sp_credentials(self):
        if (self.__sp_credentials is None):
            self.__sp_credentials = ServicePrincipalCredentials(client_id=self.__credentials.getData('client_id'),
                                                                secret=self.__credentials.getData('client_secret'),
                                                                tenant=self.__credentials.getData('tenant_id')
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
        return [i for i in self.compute_mgmt_client().virtual_machines.list_all()]

    def list_resource_groups(self):
        return [r for r in self.resource_mgmt_client().resource_groups.list()]

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
    o = o.filter(provider=ProviderChoice.AZURE)
    o = o.update(active=False)

    for i in instances:
        db.update_or_create_instance(
            provider=ProviderChoice.AZURE,
            instance_id=i.name,
            region=i.location,
            csp_info=_instance_to_json(i))

    o = Instance.objects
    o = o.filter(provider=ProviderChoice.AZURE, active=False)
    o = o.update(state=StateChoice.DELETED)
