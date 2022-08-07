from .provider import Provider, Image
from webui.settings import PCWConfig
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from msrest.exceptions import AuthenticationError
import re
import time
from typing import Dict


class Azure(Provider):
    __instances: Dict[str, "Azure"] = dict()

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.__resource_group = PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', namespace)
        self.check_credentials()

    def __new__(cls, vault_namespace):
        if vault_namespace not in Azure.__instances:
            Azure.__instances[vault_namespace] = self = object.__new__(cls)
            self.__compute_mgmt_client = None
            self.__sp_credentials = None
            self.__resource_mgmt_client = None
            self.__blob_service_client = None
        return Azure.__instances[vault_namespace]

    def subscription(self):
        return self.getData('subscription_id')

    def check_credentials(self):
        for i in range(1, 40):
            try:
                self.list_resource_groups()
                return True
            except AuthenticationError:
                self.log_info("Check credentials failed (attemp:{}) - client_id {}", i, self.getData('client_id'))
                time.sleep(1)
        raise AuthenticationError("Invalid Azure credentials")

    def bs_client(self):
        if (self.__blob_service_client is None):
            storage_account = PCWConfig.get_feature_property(
                'cleanup', 'azure-storage-account-name', self._namespace)
            storage_key = self.get_storage_key(storage_account)
            connection_string = "{};AccountName={};AccountKey={};EndpointSuffix=core.windows.net".format(
                "DefaultEndpointsProtocol=https", storage_account, storage_key)
            self.__blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        return self.__blob_service_client

    def container_client(self, container_name):
        return self.bs_client().get_container_client(container_name)

    def sp_credentials(self):
        if (self.__sp_credentials is None):
            self.__sp_credentials = ClientSecretCredential(client_id=self.getData(
                'client_id'), client_secret=self.getData('client_secret'), tenant_id=self.getData('tenant_id'))
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

    def get_storage_key(self, storage_account):
        storage_client = StorageManagementClient(self.sp_credentials(), self.subscription())
        storage_keys = storage_client.storage_accounts.list_keys(self.__resource_group, storage_account)
        storage_keys = [v.value for v in storage_keys.keys]
        return storage_keys[0]

    def list_instances(self):
        return [i for i in self.compute_mgmt_client().virtual_machines.list_all()]

    def list_resource_groups(self):
        return [r for r in self.resource_mgmt_client().resource_groups.list()]

    def delete_resource(self, resource_id):
        if self.dry_run:
            self.log_info("Deletion of resource group {} skipped due to dry run mode", resource_id)
        else:
            self.resource_mgmt_client().resource_groups.begin_delete(resource_id)

    def list_images_by_resource_group(self, resource_group):
        return self.list_by_resource_group(resource_group,
                                           filters="resourceType eq 'Microsoft.Compute/images'")

    def list_disks_by_resource_group(self, resource_group):
        return self.list_by_resource_group(resource_group,
                                           filters="resourceType eq 'Microsoft.Compute/disks'")

    def list_by_resource_group(self, resource_group, filters=None):
        return [item for item in self.resource_mgmt_client().resources.list_by_resource_group(
            resource_group, filter=filters)]

    def get_keeping_image_names(self):
        images = list()
        for item in self.container_client('sle-images').list_blobs():
            m = self.parse_image_name(item.name)
            if m:
                images.append(Image(item.name, flavor=m['key'], build=m['build'], date=item.last_modified))
            else:
                self.log_err("Unable to parse image name '{}'", item.name)

        return super().get_keeping_image_names(images)

    def cleanup_all(self):
        ''' Cleanup all autodateed data which might created during automated tests.'''
        self.cleanup_bootdiagnostics()

        keep_images = self.get_keeping_image_names()
        self.cleanup_sle_images_container(keep_images)
        self.cleanup_disks_from_rg(keep_images)
        self.cleanup_images_from_rg(keep_images)
        for i in keep_images:
            self.log_info("Keep image {} ", i)

    def cleanup_bootdiagnostics(self):
        containers = self.bs_client().list_containers()
        for c in containers:
            self.log_dbg('Found container {}', c.name)
            if (re.match('^bootdiagnostics-', c.name)):
                self.cleanup_bootdiagnostics_container(c)

    def cleanup_bootdiagnostics_container(self, container):
        latest_modification = container.last_modified
        container_blobs = self.container_client(container.name).list_blobs()
        for blob in container_blobs:
            if (latest_modification > blob.last_modified):
                latest_modification = blob.last_modified
        if (self.older_than_min_age(latest_modification)):
            self.log_info("Mark container for deletion {}", container.name)
            if self.dry_run:
                self.log_info("Deletion of boot diagnostic container {} skipped due to dry run mode", container.name)
            else:
                self.bs_client().delete_container(container.name)

    def parse_image_name(self, img_name):
        regexes = [
            # SLES12-SP5-Azure.x86_64-0.9.1-SAP-BYOS-Build3.3.vhd
            re.compile(r"""
                       SLES
                       (?P<version>\d+(-SP\d+)?)
                       -Azure\.
                       (?P<arch>[^-]+)
                       -
                       (?P<kiwi>\d+\.\d+\.\d+)
                       -
                       (?P<flavor>[-\w]+)
                       -
                       Build(?P<build>\d+\.\d+)
                       \.vhd
                       """,
                       re.X),

            # SLES15-SP2-BYOS.x86_64-0.9.3-Azure-Build1.10.vhd
            # SLES15-SP2.x86_64-0.9.3-Azure-Basic-Build1.11.vhd
            # SLES15-SP2-SAP-BYOS.x86_64-0.9.2-Azure-Build1.9.vhd
            # SLES15-SP4-BYOS.x86_64-0.9.1-Azure-Build150400.2.103.vhd
            re.compile(r"""
                       SLES
                       (?P<version>\d+(-SP\d+)?)
                       (-(?P<type>[^\.]+))?\.
                       (?P<arch>[^-]+)
                       -
                       (?P<kiwi>\d+\.\d+\.\d+)
                       (-(?P<flavor>Azure[-\w]*))?
                       -
                       Build(\d+\.)?(?P<build>\d+\.\d+)
                       \.vhd
                       """,
                       re.X)
        ]
        return self.parse_image_name_helper(img_name, regexes)

    def cleanup_sle_images_container(self, keep_images):
        container_client = self.container_client('sle-images')
        for img in container_client.list_blobs():
            m = self.parse_image_name(img.name)
            if m:
                self.log_dbg('Blob {} is candidate for deletion with build {} ', img.name, m['build'])

                if img.name not in keep_images:
                    self.log_info("Delete blob '{}'", img.name)
                    if self.dry_run:
                        self.log_info("Deletion of blob image {} skipped due to dry run mode", img.name)
                    else:
                        container_client.delete_blob(img.name, delete_snapshots="include")

    def cleanup_images_from_rg(self, keep_images):
        for item in self.list_images_by_resource_group(self.__resource_group):
            m = self.parse_image_name(item.name)
            if m:
                self.log_dbg('Image {} is candidate for deletion with build {} ', item.name, m['build'])
                if item.name not in keep_images:
                    self.log_info("Delete image '{}'", item.name)
                    if self.dry_run:
                        self.log_info("Deletion of image {} skipped due to dry run mode", item.name)
                    else:
                        self.compute_mgmt_client().images.delete(self.__resource_group, item.name)

    def cleanup_disks_from_rg(self, keep_images):
        for item in self.list_disks_by_resource_group(self.__resource_group):
            m = self.parse_image_name(item.name)
            if m:
                self.log_dbg('Disk {} is candidate for deletion with build {} ', item.name, m['build'])

                if item.name not in keep_images:
                    if self.compute_mgmt_client().disks.get(self.__resource_group, item.name).managed_by:
                        self.log_warn("Disk is in use - unable delete {}", item.name)
                    else:
                        self.log_info("Delete disk '{}'", item.name)
                        if self.dry_run:
                            self.log_info("Deletion of image {} skipped due to dry run mode", item.name)
                        else:
                            self.compute_mgmt_client().disks.begin_delete(self.__resource_group, item.name)
