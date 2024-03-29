import os
import kubernetes
import googleapiclient.discovery
from google.oauth2 import service_account
from ocw.lib.gce import GCE
from ocw.lib.k8s import clean_jobs, clean_namespaces


class GKE(GCE):
    __instances = {}

    def __new__(cls, namespace):
        if namespace not in GKE.__instances:
            GKE.__instances[namespace] = self = object.__new__(cls)
            self.__gke_client = None
            self.__kubectl_client = {}
        return GKE.__instances[namespace]

    def gke_client(self):
        if self.__gke_client is None:
            credentials = service_account.Credentials.from_service_account_info(self.private_key_data)
            self.__gke_client = googleapiclient.discovery.build('container', 'v1', credentials=credentials)
        return self.__gke_client

    def kubectl_client(self, zone: str, cluster: dict[str, str]):
        cluster_name = cluster["name"]
        zone_cluster = f"{zone}/{cluster_name}"
        if zone_cluster not in self.__kubectl_client:
            kube_dir = "~/.kube"
            kubeconfig = f"{kube_dir}/gke_config_{zone}_{cluster_name}"
            kubeconfig = os.path.expanduser(kubeconfig)
            cred = self.get_creds_location()

            res = self.cmd_exec(f"gcloud auth login  --project={self.project} --cred-file={cred} --quiet")
            if res.returncode != 0:
                raise Exception(f"gcloud auth login failed because {res.stderr}")

            res = self.cmd_exec(f"gcloud container clusters get-credentials {cluster_name} " +
                                f"--zone {zone} --project {self.project}", aditional_env={"KUBECONFIG": kubeconfig})
            if res.returncode != 0:
                raise Exception(f"Failed to get credentials for cluster {cluster_name} zone {zone} " +
                                f"and project {self.project} with the oputput {res.stderr}")

            if not os.path.exists(kubeconfig):
                raise FileNotFoundError(f"{kubeconfig} doesn't exists")

            kubernetes.config.load_kube_config(config_file=kubeconfig)
            self.__kubectl_client[zone_cluster] = kubernetes.client
        return self.__kubectl_client[zone_cluster]

    def get_clusters(self, zone: str) -> list[str]:
        request = self.gke_client().projects().zones().clusters().list(projectId=self.project, zone=zone)
        response = request.execute()
        return response.get("clusters", [])

    def cleanup_k8s_jobs(self):
        self.log_info("Cleanup jobs in GKE clusters")
        for region in self.list_regions():
            for zone in self.list_zones(region):
                for cluster in self.get_clusters(zone):
                    cluster_name = cluster["name"]
                    self.log_info(f"Cleaning jobs in GKE cluster {cluster_name} in zone {zone}")
                    client = self.kubectl_client(zone, cluster).BatchV1Api()
                    clean_jobs(self, client, cluster_name)

    def cleanup_k8s_namespaces(self):
        self.log_info("Cleanup namespaces in GKE clusters")
        for region in self.list_regions():
            for zone in self.list_zones(region):
                for cluster in self.get_clusters(zone):
                    cluster_name = cluster["name"]
                    self.log_info(f"Cleaning namespaces in GKE cluster {cluster_name} in zone {zone}")
                    client = self.kubectl_client(zone, cluster).CoreV1Api()
                    clean_namespaces(self, client)
