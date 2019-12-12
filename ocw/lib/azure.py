from .provider import Provider
from ..lib.vault import AzureCredential
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import BlockBlobService
from msrest.exceptions import AuthenticationError
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from distutils.version import LooseVersion
import re
import time
import logging

logger = logging.getLogger(__name__)


class Azure(Provider):
    __instances = dict()

    def __new__(cls, vault_namespace):
        if vault_namespace not in Azure.__instances:
            Azure.__instances[vault_namespace] = self = object.__new__(cls)
            self.__credentials = AzureCredential(vault_namespace)
            self.__compute_mgmt_client = None
            self.__sp_credentials = None
            self.__resource_mgmt_client = None

        Azure.__instances[vault_namespace].check_credentials()
        return Azure.__instances[vault_namespace]

    def subscription(self):
        return self.__credentials.getData('subscription_id')

    def check_credentials(self):
        if self.__credentials.isValid():
            self.__sp_credentials = None
            self.__credentials.renew()

        for i in range(1, 40):
            try:
                self.sp_credentials()
                return True
            except AuthenticationError:
                logger.info("check_credentials failed (attemp:%d) - for client_id %s should expire at %s",
                            i, self.__credentials.getData('client_id'),
                            self.__credentials.getAuthExpire())
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

    def cleanup_all(self):
        ''' Cleanup all autodateed data which might created during automated tests.'''
        resourcegroup = self.cfgGet('cleanup', 'azure-storage-resourcegroup')
        storage_account = self.cfgGet('cleanup', 'azure-storage-account-name')
        storage_client = StorageManagementClient(self.sp_credentials(), self.subscription())
        storage_keys = storage_client.storage_accounts.list_keys(resourcegroup, storage_account)
        storage_keys = [v.value for v in storage_keys.keys]
        block_blob_service = BlockBlobService(account_name='openqa', account_key=storage_keys[0])

        containers = block_blob_service.list_containers()
        for c in containers:
            logger.debug('Found container {}'.format(c.name))
            if (re.match('^bootdiagnostics-', c.name)):
                self.cleanup_bootdiagnostics_container(block_blob_service, c)
            if (c.name == 'sle-images'):
                self.cleanup_sle_images_container(block_blob_service, c)

    def cleanup_bootdiagnostics_container(self, bbsrv, container):
        timeout = datetime.now(timezone.utc) + timedelta(hours=24)
        last_modified = container.properties.last_modified
        generator = bbsrv.list_blobs(container.name)
        for blob in generator:
            if (last_modified < blob.properties.last_modified):
                last_modified = blob.properties.last_modified
        if (timeout > last_modified):
            logger.info("[Azure] Delete container {}".format(container.name))
            if not bbsrv.delete_container(container.name):
                logger.error("Failed to delete container {}".format(container.name))

    def cleanup_sle_images_container(self, bbsrv, container):
        generator = bbsrv.list_blobs(container.name)
        images = dict()
        for img in generator:
            logger.debug('Found image {}'.format(img.name))
            # SLES12-SP5-Azure.x86_64-0.9.1-SAP-BYOS-Build3.3.vhd
            regex = re.compile(r"""
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
                               re.X)
            m = re.match(regex, img.name)
            if (m):
                key = '-'.join([m.group('version'), m.group('flavor'), m.group('arch')])
                if key not in images:
                    images[key] = list()

                images[key].append({
                        'build': "-".join([m.group('kiwi'), m.group('build')]),
                        'name': img.name,
                        'last_modified': img.properties.last_modified,
                        })
            else:
                logger.error("Unable to parse image name '{}'".format(img.name))

        for key in images:
            images[key].sort(key=lambda x: LooseVersion(x['build']))

        max_images_per_flavor = self.cfgGet('cleanup', 'max-images-per-flavor')
        max_images_age = datetime.now(timezone.utc) - timedelta(hours=int(
                                                                self.cfgGet('cleanup', 'max-images-age-hours')))
        for img_list in images.values():
            for i in range(0, len(img_list)):
                img = img_list[i]
                if (i < len(img_list) - max_images_per_flavor or img['last_modified'] < max_images_age):
                    logger.info("[Azure] Delete image '{}'".format(img['name']))
                    bbsrv.delete_blob(container.name, img['name'], snapshot=None)
