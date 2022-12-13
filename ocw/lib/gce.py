from datetime import timezone
from dateutil.parser import parse
import googleapiclient.discovery
from google.oauth2 import service_account
from .provider import Provider


class GCE(Provider):
    __instances = {}

    def __new__(cls, vault_namespace):
        if vault_namespace not in GCE.__instances:
            GCE.__instances[vault_namespace] = self = object.__new__(cls)
            self.__compute_client = None
            self.__project = None
        return GCE.__instances[vault_namespace]

    def compute_client(self):
        self.private_key_data = self.get_data()
        self.__project = self.private_key_data["project_id"]
        if self.__compute_client is None:
            credentials = service_account.Credentials.from_service_account_info(self.private_key_data)
            self.__compute_client = googleapiclient.discovery.build(
                "compute", "v1", credentials=credentials, cache_discovery=False
            )
        return self.__compute_client

    def list_instances(self, zone):
        """ List all instances by zone."""
        result = []
        request = (
            self.compute_client().instances().list(project=self.__project, zone=zone)
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
        for region in self.list_regions():
            for zone in self.list_zones(region):
                result += self.list_instances(zone=zone)
        return result

    def list_regions(self):
        """Walk through all regions->zones and collect all instances to return them as list.
        @see https://cloud.google.com/compute/docs/reference/rest/v1/instances/list#examples"""
        result = []
        request = self.compute_client().regions().list(project=self.__project)
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
            .get(project=self.__project, region=region)
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
                project=self.__project, zone=zone, instance=instance_id
            ).execute()

    @staticmethod
    def url_to_name(url):
        return url[url.rindex("/")+1:]

    def cleanup_all(self):
        request = self.compute_client().images().list(project=self.__project)
        while request is not None:
            response = request.execute()
            if "items" not in response:
                break
            for image in response["items"]:
                if self.is_outdated(parse(image["creationTimestamp"]).astimezone(timezone.utc)):
                    if self.dry_run:
                        self.log_info("Deletion of image {} skipped due to dry run mode", image["name"])
                    else:
                        self.log_info("Delete image '{}'", image["name"])
                        request = (
                            self.compute_client()
                            .images()
                            .delete(project=self.__project, image=image["name"])
                        )
                        response = request.execute()
                        if "error" in response:
                            for err in response["error"]["errors"]:
                                self.log_err(err["message"])
                        if "warnings" in response:
                            for warn in response["warnings"]:
                                self.log_warn(warn["message"])

            request = (
                self.compute_client()
                .images()
                .list_next(previous_request=request, previous_response=response)
            )
