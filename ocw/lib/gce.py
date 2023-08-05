import contextlib
import json
from os.path import basename
from datetime import timezone
from dateutil.parser import parse
import googleapiclient.discovery
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from .provider import Provider


class GCE(Provider):
    __instances = {}
    __skip_networks = frozenset({"default"})

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

    def _delete_resource(self, api_call, resource_name, *_, **kwargs) -> None:
        resource_type = {
            self.compute_client().disks: "disk",
            self.compute_client().firewalls: "firewall",
            self.compute_client().forwardingRules: "forwardingRule",
            self.compute_client().images: "image",
            self.compute_client().instances: "instance",
            self.compute_client().networks: "network",
            self.compute_client().routes: "route",
            self.compute_client().subnetworks: "subnetwork",
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
            elif GCE.get_error_reason(err) == 'badRequest':
                # These are system generated routes when you create a network. These
                # will be deleted by the deletion of the network and do not block the
                # deletion of that network.
                # There are no properties on the Route struct that indicate a route is a
                # default one. Typically, the name will contain the word "default" or the
                # description will contain the word "Default" but a property like Kind
                # returns "compute#route" for all routes.
                # All this creating false alarms in log which we want to prevent.
                # Only way to prevent is mute error
                if resource_type.title() == "Route" and "The local route cannot be deleted" in str(err):
                    self.log_info("Skip deletion of local route")
                else:
                    self.log_err(f"{resource_type.title()} '{resource_name}' can not be deleted. Error : {err}")
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
        return [basename(z) for z in region["zones"]]

    def delete_instance(self, instance_id, zone) -> None:
        self._delete_resource(
            self.compute_client().instances, instance_id, project=self.project, zone=zone, instance=instance_id
        )

    @staticmethod
    def get_error_reason(error: "googleapiclient.errors.HttpError") -> str:
        with contextlib.suppress(KeyError, ValueError, IndexError):
            return json.loads(error.content)['error']['errors'][0]['reason']
        return "unknown"

    def cleanup_all(self) -> None:
        self.log_info("Call cleanup_all")
        self.cleanup_disks()
        self.cleanup_images()
        self.cleanup_firewalls()
        self.cleanup_forwarding_rules()
        self.cleanup_routes()
        self.cleanup_subnetworks()
        self.cleanup_networks()

    def cleanup_disks(self) -> None:
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

    def cleanup_images(self) -> None:
        self.log_dbg("Images cleanup")
        images = self._paginated(self.compute_client().images, project=self.project)
        self.log_dbg(f"{len(images)} images found")
        for image in images:
            if self.is_outdated(parse(image["creationTimestamp"]).astimezone(timezone.utc)):
                self._delete_resource(
                    self.compute_client().images, image["name"], project=self.project, image=image["name"]
                )

    def cleanup_firewalls(self) -> None:
        self.log_dbg("Firewalls cleanup")
        firewalls = [
            firewall for firewall in self._paginated(self.compute_client().firewalls, project=self.project)
            if basename(firewall["network"]) not in self.__skip_networks
        ]
        self.log_dbg(f"{len(firewalls)} firewalls found")
        for firewall in firewalls:
            if self.is_outdated(parse(firewall["creationTimestamp"]).astimezone(timezone.utc)):
                self._delete_resource(
                    self.compute_client().firewalls, firewall["name"], project=self.project, firewall=firewall["name"]
                )

    def cleanup_forwarding_rules(self) -> None:
        self.log_dbg("Forwarding rules cleanup")
        for region in self.list_regions():
            rules = [
                rule for rule in self._paginated(self.compute_client().forwardingRules, project=self.project, region=region)
                if basename(rule["network"]) not in self.__skip_networks
            ]
            self.log_dbg(f"{len(rules)} forwarding_rules found")
            for rule in rules:
                if self.is_outdated(parse(rule["creationTimestamp"]).astimezone(timezone.utc)):
                    self._delete_resource(
                        self.compute_client().forwardingRules, rule["name"],
                        project=self.project, region=region, forwardingRule=rule["name"]
                    )

    def cleanup_routes(self) -> None:
        self.log_dbg("Routes cleanup")
        routes = [
            route for route in self._paginated(self.compute_client().routes, project=self.project)
            if basename(route["network"]) not in self.__skip_networks
        ]
        self.log_dbg(f"{len(routes)} routes found")
        for route in routes:
            if self.is_outdated(parse(route["creationTimestamp"]).astimezone(timezone.utc)):
                self._delete_resource(
                    self.compute_client().routes, route["name"], project=self.project, route=route["name"]
                )

    def cleanup_subnetworks(self) -> None:
        self.log_dbg("Subnetworks cleanup")
        for region in self.list_regions():
            subnetworks = [
                subnet for subnet in self._paginated(self.compute_client().subnetworks, project=self.project, region=region)
                if basename(subnet["network"]) not in self.__skip_networks
            ]
            self.log_dbg(f"{len(subnetworks)} subnetworks found in region {region}")
            for subnetwork in subnetworks:
                if self.is_outdated(parse(subnetwork["creationTimestamp"]).astimezone(timezone.utc)):
                    self._delete_resource(
                        self.compute_client().subnetworks, subnetwork["name"],
                        project=self.project, region=region, subnetwork=subnetwork["name"]
                    )

    def cleanup_networks(self) -> None:
        self.log_dbg("Networks cleanup")
        networks = [
            network for network in self._paginated(self.compute_client().networks, project=self.project)
            if network["name"] not in self.__skip_networks
        ]
        self.log_dbg(f"{len(networks)} networks found")
        for network in networks:
            if self.is_outdated(parse(network["creationTimestamp"]).astimezone(timezone.utc)):
                self._delete_resource(
                    self.compute_client().networks, network["name"], project=self.project, network=network["name"]
                )
