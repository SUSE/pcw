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

    def _paginated(self, api_call, **kwargs) -> list:
        results = []
        request = api_call().list(**kwargs)
        while request is not None:
            response = request.execute()
            if "items" in response:
                results.extend(response["items"])
            else:
                self.log_dbg(f"response has no items. id={response.get('id')}")
            request = api_call().list_next(previous_request=request, previous_response=response)
        return results

    def _delete_resource(self, api_call, resource_name, *args, **kwargs) -> None:
        resource_type = {
            self.compute_client().instances: "instance",
            self.compute_client().images: "image",
            self.compute_client().disks: "disk",
        }.get(api_call, "resource")
        if self.dry_run:
            self.log_info(f"Deletion of {resource_type} {resource_name} skipped due to dry run mode")
            return
        request = api_call().delete(**kwargs)
        try:
            self.log_info(f"Delete {resource_type.title()} '{resource_name}'")
            response = request.execute()
            self.log_dbg(f"Deletion response: {response}")
            self.log_info(f"{resource_type.title()} '{resource_name}' deleted")
        except HttpError as err:
            if GCE.get_error_reason(err) == 'resourceInUseByAnotherResource':
                self.log_dbg(f"{resource_type.title()} '{resource_name}' can not be deleted because in use")
            else:
                raise err

    def compute_client(self):
        if self.__compute_client is None:
            credentials = service_account.Credentials.from_service_account_info(self.private_key_data)
            self.__compute_client = googleapiclient.discovery.build(
                "compute", "v1", credentials=credentials, cache_discovery=False
            )
        return self.__compute_client

    def list_instances(self, zone) -> list:
        """ List all instances by zone."""
        self.log_dbg(f"Call list_instances for {zone}")
        return self._paginated(self.compute_client().instances, project=self.project, zone=zone)

    def list_all_instances(self) -> list:
        result = []
        self.log_dbg("Call list_all_instances")
        for region in self.list_regions():
            for zone in self.list_zones(region):
                result.extend(self.list_instances(zone=zone))
        return result

    def list_regions(self) -> list:
        """Walk through all regions->zones and collect all instances to return them as list.
        @see https://cloud.google.com/compute/docs/reference/rest/v1/instances/list#examples"""
        regions = self._paginated(self.compute_client().regions, project=self.project)
        return [region["name"] for region in regions]

    def list_zones(self, region) -> list:
        region = (
            self.compute_client()
            .regions()
            .get(project=self.project, region=region)
            .execute()
        )
        return [GCE.url_to_name(z) for z in region["zones"]]

    def delete_instance(self, instance_id, zone) -> None:
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
    def url_to_name(url) -> str:
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

    def cleanup_all(self) -> None:
        self.log_info("Call cleanup_all")

        self.log_dbg("Disks cleanup")
        for region in self.list_regions():
            for zone in self.list_zones(region):
                self.log_dbg(f"Searching for disks in {zone}")
                disks = self._paginated(self.compute_client().disks, project=self.project, zone=zone)
                self.log_dbg(f"{len(disks)} disks found")
                for disk in disks:
                    if self.is_outdated(parse(disk["creationTimestamp"]).astimezone(timezone.utc)):
                        self._delete_resource(
                            self.compute_client().disks, disk["name"], project=self.project, zone=zone, disk=disk["name"]
                        )

        self.log_dbg("Images cleanup")
        images = self._paginated(self.compute_client().images, project=self.project)
        self.log_dbg(f"{len(images)} images found")
        for image in images:
            if self.is_outdated(parse(image["creationTimestamp"]).astimezone(timezone.utc)):
                self._delete_resource(
                    self.compute_client().images, image["name"], project=self.project, image=image["name"]
                )
