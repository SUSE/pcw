import re
import time
from typing import Dict
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from msrest.exceptions import AuthenticationError
from webui.settings import PCWConfig
from .provider import Provider
from ..models import Instance


class Azure(Provider):
    __instances: Dict[str, "Azure"] = {}

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.__resource_group = PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', namespace)
        self.check_credentials()

    def __new__(cls, vault_namespace: str) -> 'Azure':
        if vault_namespace not in Azure.__instances:
            Azure.__instances[vault_namespace] = self = object.__new__(cls)
            self.__compute_mgmt_client = None
            self.__sp_credentials = None
            self.__resource_mgmt_client = None
            self.__blob_service_client = None
        return Azure.__instances[vault_namespace]

    def subscription(self) -> str:
        return self.get_data('subscription_id')

    def check_credentials(self) -> bool:
        for i in range(1, 5):
            try:
                self.list_resource_groups()
                return True
            except AuthenticationError:
                self.log_info("Check credentials failed (attemp:{}) - client_id {}", i, self.get_data('client_id'))
                time.sleep(1)
        raise AuthenticationError("Invalid Azure credentials")

    def bs_client(self):
        if self.__blob_service_client is None:
            storage_account = PCWConfig.get_feature_property(
                'cleanup', 'azure-storage-account-name', self._namespace)
            storage_key = self.get_storage_key(storage_account)
            connection_string = "{};AccountName={};AccountKey={};EndpointSuffix=core.windows.net".format(
                "DefaultEndpointsProtocol=https", storage_account, storage_key)
            self.__blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        return self.__blob_service_client

    def container_client(self, container_name: str):
        return self.bs_client().get_container_client(container_name)

    def sp_credentials(self):
        if self.__sp_credentials is None:
            self.__sp_credentials = ClientSecretCredential(client_id=self.get_data(
                'client_id'), client_secret=self.get_data('client_secret'), tenant_id=self.get_data('tenant_id'))
        return self.__sp_credentials

    def compute_mgmt_client(self):
        if self.__compute_mgmt_client is None:
            self.__compute_mgmt_client = ComputeManagementClient(
                self.sp_credentials(), self.subscription())
        return self.__compute_mgmt_client

    def resource_mgmt_client(self):
        if self.__resource_mgmt_client is None:
            self.__resoure_mgmt_client = ResourceManagementClient(
                self.sp_credentials(), self.subscription())
        return self.__resoure_mgmt_client

    def get_storage_key(self, storage_account: str) -> str:
        storage_client = StorageManagementClient(self.sp_credentials(), self.subscription())
        storage_keys = storage_client.storage_accounts.list_keys(self.__resource_group, storage_account)
        storage_keys = [v.value for v in storage_keys.keys]
        return storage_keys[0]

    def list_instances(self) -> list:
        return list(self.compute_mgmt_client().virtual_machines.list_all())

    def get_vm_types_in_resource_group(self, resource_group: str) -> str:
        self.log_dbg("Listing VMs for {}", resource_group)
        vms = self.compute_mgmt_client().virtual_machines.list(resource_group)
        type_str = "N/A"
        for azure_vm in vms:
            if type_str == "N/A":
                type_str = azure_vm.hardware_profile.vm_size
            else:
                type_str = "{},{}".format(type_str, azure_vm.hardware_profile.vm_size)
                self.log_warn('{} resource group has more than one VM', resource_group)
        return type_str

    def list_resource_groups(self) -> list:
        return list(self.resource_mgmt_client().resource_groups.list())

    def delete_resource(self, resource_id: str) -> None:
        if self.dry_run:
            self.log_info("Deletion of resource group {} skipped due to dry run mode", resource_id)
        else:
            self.log_info("Deleting of resource group {}", resource_id)
            self.resource_mgmt_client().resource_groups.begin_delete(resource_id)

    def list_images_by_resource_group(self, resource_group):
        return self.list_by_resource_group(resource_group,
                                           filters="resourceType eq 'Microsoft.Compute/images'")

    def list_disks_by_resource_group(self, resource_group):
        return self.list_by_resource_group(resource_group,
                                           filters="resourceType eq 'Microsoft.Compute/disks'")

    def list_by_resource_group(self, resource_group, filters=None) -> list:
        return list(self.resource_mgmt_client().resources.list_by_resource_group(
            resource_group, filter=filters, expand="changedTime"))

    def cleanup_all(self) -> None:
        self.log_dbg("Call cleanup_all")
        self.cleanup_images_from_rg()
        self.cleanup_disks_from_rg()
        self.cleanup_blob_containers()

    @staticmethod
    def container_valid_for_cleanup(container) -> bool:
        '''
            under term "container" we meant Azure Blob Storage Container.
            See https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-introduction
            for more details
            Container is valid for cleanup if it met 2 conditions :
            1. "metadata" of container does not contain special tag (pcw_ignore)
            2. Container name or contains "bootdiagnostics-" in its name or its name is "sle-images"
        '''
        if Instance.TAG_IGNORE in container['metadata']:
            return False
        if re.match('^bootdiagnostics-', container.name):
            return True
        if container.name == 'sle-images':
            return True
        return False

    def cleanup_blob_containers(self) -> None:
        self.log_dbg("Call cleanup_blob_containers")
        containers = self.bs_client().list_containers(include_metadata=True)
        for container in containers:
            if Azure.container_valid_for_cleanup(container):
                self.log_dbg('Found container {}', container.name)
                container_blobs = self.container_client(container.name).list_blobs()
                for blob in container_blobs:
                    if self.is_outdated(blob.last_modified):
                        if self.dry_run:
                            self.log_info("Deletion of blob {} skipped due to dry run mode", blob.name)
                        else:
                            self.log_info("Deleting blob {}", blob.name)
                            self.container_client(container.name).delete_blob(blob.name, delete_snapshots="include")

    def cleanup_images_from_rg(self) -> None:
        self.log_dbg("Call cleanup_images_from_rg")
        for item in self.list_images_by_resource_group(self.__resource_group):
            if self.is_outdated(item.changed_time):
                if self.dry_run:
                    self.log_info("Deletion of image {} skipped due to dry run mode", item.name)
                else:
                    self.log_info("Delete image '{}'", item.name)
                    self.compute_mgmt_client().images.begin_delete(self.__resource_group, item.name)

    def cleanup_disks_from_rg(self) -> None:
        self.log_dbg("Call cleanup_disks_from_rg")
        for item in self.list_disks_by_resource_group(self.__resource_group):
            if self.is_outdated(item.changed_time):
                if self.compute_mgmt_client().disks.get(self.__resource_group, item.name).managed_by:
                    self.log_warn("Disk is in use - unable delete {}", item.name)
                else:
                    if self.dry_run:
                        self.log_info("Deletion of disk {} skipped due to dry run mode", item.name)
                    else:
                        self.log_info("Delete disk '{}'", item.name)
                        self.compute_mgmt_client().disks.begin_delete(self.__resource_group, item.name)
