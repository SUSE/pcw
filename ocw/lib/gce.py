import json
from datetime import timezone
from dateutil.parser import parse
import googleapiclient.discovery
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from .provider import Provider


class GCE(Provider):
    __instances = {}

    def __new__(cls, vault_namespace):
        if vault_namespace not in GCE.__instances:
            GCE.__instances[vault_namespace] = object.__new__(cls)
        return GCE.__instances[vault_namespace]

    def __init__(self, namespace):
        super().__init__(namespace)
        self.__compute_client = None
        self.private_key_data = self.get_data()
        self.project = self.private_key_data["project_id"]

    def compute_client(self):
        if self.__compute_client is None:
            credentials = service_account.Credentials.from_service_account_info(self.private_key_data)
            self.__compute_client = googleapiclient.discovery.build(
                "compute", "v1", credentials=credentials, cache_discovery=False
            )
        return self.__compute_client

    def list_instances(self, zone):
        """ List all instances by zone."""
        self.log_dbg("Call list_instances for {}", zone)
        result = []
        request = (
            self.compute_client().instances().list(project=self.project, zone=zone)
        )
        while request is not None:
            response = request.execute()
            if "items" in response:
                result += response["items"]
            request = (
                self.compute_client()
                .instances()
                .list_next(previous_request=request, previous_response=response)
            )
        return result

    def list_all_instances(self):
        result = []
        self.log_dbg("Call list_all_instances")
        for region in self.list_regions():
            for zone in self.list_zones(region):
                result += self.list_instances(zone=zone)
        return result

    def list_regions(self):
        """Walk through all regions->zones and collect all instances to return them as list.
        @see https://cloud.google.com/compute/docs/reference/rest/v1/instances/list#examples"""
        result = []
        request = self.compute_client().regions().list(project=self.project)
        while request is not None:
            response = request.execute()

            for region in response["items"]:
                result.append(region["name"])
            request = (
                self.compute_client()
                .regions()
                .list_next(previous_request=request, previous_response=response)
            )
        return result

    def list_zones(self, region):
        region = (
            self.compute_client()
            .regions()
            .get(project=self.project, region=region)
            .execute()
        )
        return [GCE.url_to_name(z) for z in region["zones"]]

    def delete_instance(self, instance_id, zone):
        if self.dry_run:
            self.log_info(
                "Deletion of instance {} skipped due to dry run mode", instance_id
            )
        else:
            self.log_info("Delete instance {}".format(instance_id))
            self.compute_client().instances().delete(
                project=self.project, zone=zone, instance=instance_id
            ).execute()

    @staticmethod
    def url_to_name(url):
        return url[url.rindex("/")+1:]

    @staticmethod
    def get_error_reason(error: "googleapiclient.errors.HttpError") -> str:
        reason = "unknown"
        try:
            error_content = json.loads(error.content)
            return error_content['error']['errors'][0]['reason']
        except (KeyError, ValueError, IndexError):
            pass
        return reason

    def cleanup_all(self):
        self.log_dbg("Call cleanup_all")

        self.log_dbg("Disks cleanup")
        for region in self.list_regions():
            for zone in self.list_zones(region):
                self.log_dbg("Searching for disks in {}", zone)
                request = self.compute_client().disks().list(project=self.project, zone=zone)
                while request is not None:
                    response = request.execute()
                    if "items" not in response:
                        break
                    for disk in response["items"]:
                        if self.is_outdated(parse(disk["creationTimestamp"]).astimezone(timezone.utc)):
                            if self.dry_run:
                                self.log_info("Deletion of disk {} created on {} skipped due to dry run mode",
                                              disk["name"], disk["creationTimestamp"])
                            else:
                                request = (
                                    self.compute_client()
                                    .disks()
                                    .delete(project=self.project, zone=zone, disk=disk["name"])
                                )
                                try:
                                    response = request.execute()
                                    self.log_info("Disk '{}' deleted", disk["name"])
                                except HttpError as err:
                                    if GCE.get_error_reason(err) == 'resourceInUseByAnotherResource':
                                        self.log_dbg("Disk {} can not be deleted because in use", disk["name"])
                                    else:
                                        raise err

                            request = (
                                self.compute_client()
                                .disks()
                                .list_next(previous_request=request, previous_response=response)
                            )

        self.log_dbg("Images cleanup")
        request = self.compute_client().images().list(project=self.project)

        while request is not None:
            response = request.execute()
            if "items" not in response:
                break
            for image in response["items"]:
                if self.is_outdated(parse(image["creationTimestamp"]).astimezone(timezone.utc)):
                    if self.dry_run:
                        self.log_info("Deletion of image {} skipped due to dry run mode", image["name"])
                    else:
                        request = (
                            self.compute_client()
                            .images()
                            .delete(project=self.project, image=image["name"])
                        )
                        try:
                            response = request.execute()
                            self.log_info("Delete image '{}'", image["name"])
                        except HttpError as err:
                            if GCE.get_error_reason(err) == 'resourceInUseByAnotherResource':
                                self.log_dbg("Image {} can not be deleted because in use", image["name"])
                            else:
                                raise err

            request = (
                self.compute_client()
                .images()
                .list_next(previous_request=request, previous_response=response)
            )
