from datetime import datetime, timezone
from typing import Dict
from dateutil.parser import parse
import openstack
from openstack.exceptions import OpenStackCloudException
from webui.PCWConfig import PCWConfig
from webui.settings import DEBUG
from .provider import Provider


class Openstack(Provider):
    __instances: Dict[str, "Openstack"] = {}

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.client()

    def __new__(cls, vault_namespace: str):
        if vault_namespace not in Openstack.__instances:
            Openstack.__instances[vault_namespace] = self = object.__new__(cls)
            self.__client = None
        return Openstack.__instances[vault_namespace]

    def client(self) -> None:
        if self.__client is None:
            self.__client = openstack.connect(
                debug=DEBUG,
                insecure=True,  # Trust the certificate
                auth_url=self.get_data('auth_url'),
                project_name=self.get_data('project_name'),
                username=self.get_data('username'),
                password=self.get_data('password'),
                region_name=self.get_data('region_name'),
                user_domain_name=self.get_data('user_domain_name'),
                project_id=self.get_data('project_id'),
                load_envvars=False,  # Avoid reading OS_* environment variables
                load_yaml_config=False,  # Avoid reading clouds.yaml
            )
        return self.__client

    def is_outdated(self, timestamp: str, param: str) -> bool:
        now = datetime.now(timezone.utc)
        max_days = PCWConfig.get_feature_property('cleanup', param, self._namespace)
        return (now - parse(timestamp).astimezone(timezone.utc)).days > max_days

    def cleanup_all(self) -> None:
        self._cleanup_instances()
        self._cleanup_images()
        self._cleanup_keypairs()

    def _cleanup_instances(self) -> None:
        # Delete VM's & associated floating IP address(es)
        try:
            servers = [vm for vm in self.client().compute.servers() if vm.name.startswith("openqa-vm-")]
        except OpenStackCloudException as exc:
            self.log_warn("Got exception while listing instances: {}", exc)
            return
        self.log_dbg("Found {} servers", len(servers))
        for server in servers:
            if self.is_outdated(server.created_at, "openstack-vm-max-age-days"):
                if self.dry_run:
                    self.log_info("Instance termination {} skipped due to dry run mode", server.name)
                else:
                    self.log_info("Deleting instance {}", server.name)
                    try:
                        if not self.client().delete_server(
                                server.name,
                                wait=False,
                                timeout=180,
                                delete_ips=True,  # Delete floating IP address
                                delete_ip_retry=1):
                            self.log_err("Failed to delete instance {}", server.name)
                    except OpenStackCloudException as exc:
                        self.log_warn("Got exception while deleting instance {}: {}", server.name, exc)

    def _cleanup_images(self) -> None:
        try:
            images = [image for image in self.client().image.images() if "openqa" in image.tags]
        except OpenStackCloudException as exc:
            self.log_warn("Got exception while listing images: {}", exc)
            return
        self.log_dbg("Found {} images", len(images))
        for image in images:
            if self.is_outdated(image.created_at, "openstack-image-max-age-days"):
                if self.dry_run:
                    self.log_info("Image deletion {} skipped due to dry run mode", image.name)
                else:
                    self.log_info("Deleting image {}", image.name)
                    try:
                        if not self.client().delete_image(
                                image.name,
                                wait=False,
                                timeout=3600):
                            self.log_err("Failed to delete image {}", image.name)
                    except OpenStackCloudException as exc:
                        self.log_warn("Got exception while deleting image {}: {}", image.name, exc)

    def _cleanup_keypairs(self) -> None:
        try:
            keypairs = [keypair for keypair in self.client().list_keypairs() if keypair.name.startswith("openqa")]
        except OpenStackCloudException as exc:
            self.log_warn("Got exception while listing keypairs: {}", exc)
            return
        self.log_dbg("Found {} keypairs", len(keypairs))
        for keypair in keypairs:
            if keypair.created_at is None:
                keypair.created_at = self.client().compute.get_keypair(keypair.name).created_at
            if self.is_outdated(keypair.created_at, "openstack-key-max-days"):
                if self.dry_run:
                    self.log_info("Keypair deletion {} skipped due to dry run mode", keypair.name)
                else:
                    self.log_info("Deleting keypair {}", keypair.name)
                    try:
                        if not self.client().delete_keypair(keypair.name):
                            self.log_err("Failed to delete keypair {}", keypair.name)
                    except OpenStackCloudException as exc:
                        self.log_warn("Got exception while deleting keypair {}: {}", keypair.name, exc)
