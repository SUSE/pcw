import time
from typing import Dict
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
from msrest.exceptions import AuthenticationError
from dateutil.parser import parse
from webui.PCWConfig import PCWConfig
from .provider import Provider
from ..models import Instance


class Azure(Provider):
    __instances: Dict[str, "Azure"] = {}

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.__resource_group: str = str(PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', namespace))
        self.check_credentials()
        self.__gallery: str = str(PCWConfig.get_feature_property('cleanup', 'azure-gallery-name', namespace))

    def __new__(cls, namespace: str) -> 'Azure':
        if namespace not in Azure.__instances:
            Azure.__instances[namespace] = self = object.__new__(cls)
            self.__compute_mgmt_client = None
            self.__sp_credentials = None
            self.__resource_mgmt_client = None
            self.__blob_service_client = None
        return Azure.__instances[namespace]

    def subscription(self) -> str:
        return self.get_data('subscription_id')

    def check_credentials(self) -> bool:
        for i in range(1, 5):
            try:
                self.list_resource_groups()
                return True
            except AuthenticationError:
                self.log_info(f"Check credentials failed (attempt:{i}) - client_id {self.get_data('client_id')}")
                time.sleep(1)
        raise AuthenticationError("Invalid Azure credentials")

    def bs_client(self):
        if self.__blob_service_client is None:
            storage_account = PCWConfig.get_feature_property(
                'cleanup', 'azure-storage-account-name', self._namespace)
            storage_key = self.get_storage_key(storage_account)
            self.__blob_service_client = BlobServiceClient.from_connection_string(
                f"DefaultEndpointsProtocol=https;AccountName={storage_account};AccountKey={storage_key};EndpointSuffix=core.windows.net"
            )
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
            self.__resource_mgmt_client = ResourceManagementClient(
                self.sp_credentials(), self.subscription())
        return self.__resource_mgmt_client

    def get_storage_key(self, storage_account: str) -> str:
        storage_client = StorageManagementClient(self.sp_credentials(), self.subscription())
        storage_keys = storage_client.storage_accounts.list_keys(self.__resource_group, storage_account)
        storage_keys = [v.value for v in storage_keys.keys]
        return storage_keys[0]

    def list_instances(self) -> list:
        return list(self.compute_mgmt_client().virtual_machines.list_all())

    def get_vm_types_in_resource_group(self, resource_group: str) -> str | None:
        self.log_dbg(f"Listing VMs for {resource_group}")
        type_set = set()
        try:
            vms = self.compute_mgmt_client().virtual_machines.list(resource_group)
            for azure_vm in vms:
                type_set.add(azure_vm.hardware_profile.vm_size)
        except ResourceNotFoundError:
            self.log_dbg(f"{resource_group} already deleted")
            return None
        return ', '.join(type_set) if type_set else "N/A"

    def get_resource_properties(self, resource_id):
        return self.resource_mgmt_client().resources.get_by_id(resource_id, api_version="2023-07-03").properties

    def list_resource_groups(self) -> list:
        return list(self.resource_mgmt_client().resource_groups.list())

    def delete_resource(self, resource_id: str) -> None:
        if self.dry_run:
            self.log_info(f"Deletion of resource group {resource_id} skipped due to dry run mode")
        else:
            self.log_info(f"Deleting of resource group {resource_id}")
            self.resource_mgmt_client().resource_groups.begin_delete(resource_id)

    def list_images(self):
        return self.list_resource(filters="resourceType eq 'Microsoft.Compute/images'")

    def list_disks(self):
        return self.list_resource(filters="resourceType eq 'Microsoft.Compute/disks'")

    def list_resource(self, filters=None) -> list:
        return list(self.resource_mgmt_client().resources.list_by_resource_group(
            self.__resource_group, filter=filters, expand="changedTime"))

    def cleanup_all(self) -> None:
        self.log_info("Call cleanup_all")
        self.cleanup_images()
        self.cleanup_gallery_img_versions()
        self.cleanup_disks()
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
        if container.name.startswith("bootdiagnostics-"):
            return True
        if container.name == 'sle-images':
            return True
        return False

    def cleanup_blob_containers(self) -> None:
        self.log_dbg("Call cleanup_blob_containers")
        containers = self.bs_client().list_containers(include_metadata=True)
        for container in containers:
            if Azure.container_valid_for_cleanup(container):
                self.log_dbg(f'Found container {container.name}')
                container_blobs = self.container_client(container.name).list_blobs()
                for blob in container_blobs:
                    if self.is_outdated(blob.last_modified):
                        if self.dry_run:
                            self.log_info(f"Deletion of blob {blob.name} skipped due to dry run mode")
                        else:
                            self.log_info(f"Deleting blob {blob.name}")
                            self.container_client(container.name).delete_blob(blob.name, delete_snapshots="include")

    def cleanup_images(self) -> None:
        self.log_dbg("Call cleanup_images")
        for item in self.list_images():
            if self.is_outdated(item.changed_time):
                if self.dry_run:
                    self.log_info(f"Deletion of image {item.name} skipped due to dry run mode")
                else:
                    self.log_info(f"Delete image '{item.name}'")
                    self.compute_mgmt_client().images.begin_delete(self.__resource_group, item.name)

    def cleanup_disks(self) -> None:
        self.log_dbg("Call cleanup_disks")
        for item in self.list_disks():
            if self.is_outdated(item.changed_time):
                if self.compute_mgmt_client().disks.get(self.__resource_group, item.name).managed_by:
                    self.log_warn(f"Disk is in use - skipping {item.name}")
                else:
                    if self.dry_run:
                        self.log_info(f"Deletion of disk {item.name} skipped due to dry run mode")
                    else:
                        self.log_info(f"Delete disk '{item.name}'")
                        self.compute_mgmt_client().disks.begin_delete(self.__resource_group, item.name)

    def cleanup_gallery_img_versions(self) -> None:
        self.log_dbg("Call cleanup_gallery_img_versions")
        gallery = self.compute_mgmt_client().galleries.get(self.__resource_group, self.__gallery)
        if Instance.TAG_IGNORE in gallery.tags:
            self.log_err(f"Gallery in resource group {self.__resource_group} has {Instance.TAG_IGNORE} tag: {self.__gallery}")
            return
        for image in self.compute_mgmt_client().gallery_images.list_by_gallery(self.__resource_group, gallery.name):
            if Instance.TAG_IGNORE in image.tags:
                self.log_info(f"Gallery {self.__gallery} image {image} has {Instance.TAG_IGNORE} tag")
                continue
            versions = list(self.compute_mgmt_client().gallery_image_versions.list_by_gallery_image(
                self.__resource_group, gallery.name, image.name))
            self.log_dbg(f"Image {image} in gallery {self.__gallery} has {len(versions)} versions")
            for version in versions:
                if version.tags is not None and Instance.TAG_IGNORE in version.tags:
                    self.log_info(f"Image version {version} for image {image} in gallery {self.__gallery} has {Instance.TAG_IGNORE} tag")
                    continue
                if version.provisioning_state == "Failed" or \
                        self.is_outdated(parse(self.get_resource_properties(version.id)['publishingProfile']['publishedDate'])):
                    if self.dry_run:
                        self.log_info(f"Deletion of version {gallery.name}/{image.name}/{version.name} skipped due to dry run mode")
                    else:
                        self.log_info(f"Delete version '{gallery.name}/{image.name}/{version.name}'")
                        self.compute_mgmt_client().gallery_image_versions.begin_delete(
                                self.__resource_group, gallery.name, image.name, version.name
                        )
            # Delete image definition if all image versions were deleted
            if not versions:
                if self.dry_run:
                    self.log_info(f"Deletion of image {gallery.name}/{image.name} skipped due to dry run mode")
                else:
                    self.log_info(f"Delete image '{gallery.name}/{image.name}'")
                    self.compute_mgmt_client().gallery_images.begin_delete(
                            self.__resource_group, gallery.name, image.name
                    )

    def get_img_versions_count(self) -> int:
        self.log_dbg("Call get_img_versions_count")
        gallery = self.compute_mgmt_client().galleries.get(self.__resource_group, self.__gallery)
        all_img_versions = 0
        for image_definition in self.compute_mgmt_client().gallery_images.list_by_gallery(self.__resource_group, gallery.name):
            img_versions = len(list(self.compute_mgmt_client().gallery_image_versions.list_by_gallery_image(
                    self.__resource_group, gallery.name, image_definition.name)))
            self.log_dbg(f"{image_definition.name} has {img_versions} versions")
            all_img_versions += img_versions
        return all_img_versions
