from ..lib.vault import AzureCredential
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from msrest.exceptions import AuthenticationError
import time
import logging


class Azure:
    __instances = dict()
    __credentials = None
    __compute_mgmt_client = None
    __sp_credentials = None
    __resource_mgmt_client = None
    __logger = None

    def __new__(cls, vault_namespace):
        if vault_namespace not in Azure.__instances:
            Azure.__instances[vault_namespace] = object.__new__(cls)
            Azure.__instances[vault_namespace].__credentials = AzureCredential(vault_namespace)
            Azure.__instances[vault_namespace].__logger = logging.getLogger(__name__)

        Azure.__instances[vault_namespace].check_credentials()
        return Azure.__instances[vault_namespace]

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
