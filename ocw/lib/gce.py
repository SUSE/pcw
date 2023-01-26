import os
import subprocess
import json
from datetime import datetime, timezone, timedelta
from dateutil.parser import parse
import googleapiclient.discovery
from google.oauth2 import service_account
from .provider import Provider
import kubernetes
from tempfile import NamedTemporaryFile
import base64



class GCE(Provider):
    __instances = {}

    def __new__(cls, vault_namespace):
        if vault_namespace not in GCE.__instances:
            GCE.__instances[vault_namespace] = self = object.__new__(cls)
            self.__compute_client = None
            self.__gke_client = None
            self.__kubectl_client = {}
        return GCE.__instances[vault_namespace]


    def get_credentials(self):
        self.private_key_data = self.get_data()
        return service_account.Credentials.from_service_account_info(self.private_key_data)

    def get_project_id(self):
        self.private_key_data = self.get_data()
        return self.private_key_data["project_id"]

    def compute_client(self):
        if self.__compute_client is None:
            credentials = self.get_credentials()
            self.__compute_client = googleapiclient.discovery.build(
                "compute", "v1", credentials=credentials, cache_discovery=False
            )
        return self.__compute_client

    def gke_client(self):
        if self.__gke_client is None:
            credentials = self.get_credentials()
            self.__gke_client = googleapiclient.discovery.build('container', 'v1', credentials=credentials)

        return self.__gke_client

    def kubectl_client(self, zone, cluster):
        cluster_name = cluster["name"]
        kube_dir = "/root/.kube"
        kubeconfig = f"{kube_dir}/gke_config_{zone}_{cluster_name}"

        #Option 1
        try:
            self.cmd_exec("gcloud auth login --cred-file=/var/pcw/qac/GCE.json")
            self.cmd_exec(f"gcloud container clusters get-credentials {cluster_name} --zone {zone} --project {self.get_project_id()}", {"KUBECONFIG": kubeconfig})
            if not os.path.exists(kubeconfig):
                raise "{kubeconfig} doesn't exists"
        except subprocess.CalledProcessError:
            self.log_err(f"Cannot get the kubeconfig for the cluster {cluster_name} on region {zone}")
            return None
        else:
            kubernetes.config.load_kube_config(config_file=kubeconfig)
            self.__kubectl_client[zone] = kubernetes.client.BatchV1Api()
            return self.__kubectl_client[zone]

        # Option 2
        # kubeconfig = "/var/pcw/qac/eks"
        # # required loging to prevent error as User \"system:anonymous\" cannot list resource \"jobs\"
        # self.cmd_exec("gcloud auth login --cred-file=/var/pcw/qac/GCE.json")
        # kubernetes.config.load_kube_config(config_file=kubeconfig)
        # self.__kubectl_client[zone] = kubernetes.client.BatchV1Api()
        # return self.__kubectl_client[zone]


    def list_instances(self, zone):
        """ List all instances by zone."""
        self.log_dbg("Call list_instances for {}", zone)
        result = []
        request = (
            self.compute_client().instances().list(project=self.get_project_id(), zone=zone)
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
        request = self.compute_client().regions().list(project=self.get_project_id())
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
            .get(project=self.get_project_id(), region=region)
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
                project=self.get_project_id(), zone=zone, instance=instance_id
            ).execute()

    @staticmethod
    def url_to_name(url):
        return url[url.rindex("/")+1:]

    def cleanup_all(self):
        request = self.compute_client().images().list(project=self.get_project_id())
        self.log_dbg("Call cleanup_all")
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
                            .delete(project=self.get_project_id(), image=image["name"])
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


    def cleanup_k8s_jobs(self):
        self.log_dbg('Call cleanup_k8s_jobs')

        credentials = self.get_credentials()

        clusters = {}
        for region in self.list_regions():
            for zone in self.list_zones(region):
                request = self.gke_client().projects().zones().clusters().list(projectId=self.get_project_id(), zone=zone)
                response = request.execute()
                if 'clusters' in response:
                    for cluster in response["clusters"]:
                        cluster_name = cluster["name"]
                        client = self.kubectl_client(zone, cluster)
                        if client is not None:
                            now = datetime.now(timezone.utc)
                            ret = client.list_job_for_all_namespaces(watch=False)
                            for job in ret.items:
                                age = (now - job.status.start_time).days
                                if age >= 1:
                                    if not self.dry_run:
                                        self.log_info(f"Deleting from {cluster_name} the job {job.metadata.name} " +
                                                    f"with age {age}")
                                        #client.delete_namespaced_job(job.metadata.name, job.metadata.namespace)
                                    else:
                                        self.log_info(f"Skip deleting from {cluster_name} the job {job.metadata.name} " +
                                                    f"with age {age}")
