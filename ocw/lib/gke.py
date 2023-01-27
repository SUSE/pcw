import os
import kubernetes
import googleapiclient.discovery
from google.oauth2 import service_account
from ocw.lib.gce import GCE
from ocw.lib.k8s import clean_jobs


class GKE(GCE):
    __instances = {}

    def __new__(cls, vault_namespace):
        if vault_namespace not in GKE.__instances:
            GKE.__instances[vault_namespace] = self = object.__new__(cls)
            self.__gke_client = None
            self.__kubectl_client = {}

        return GKE.__instances[vault_namespace]

    def gke_client(self):
        if self.__gke_client is None:
            credentials = service_account.Credentials.from_service_account_info(self.private_key_data)
            self.__gke_client = googleapiclient.discovery.build('container', 'v1', credentials=credentials)

        return self.__gke_client

    def kubectl_client(self, zone, cluster):
        cluster_name = cluster["name"]
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
        self.__kubectl_client[zone] = kubernetes.client.BatchV1Api()
        return self.__kubectl_client[zone]

    def get_clusters(self, zone):
        request = self.gke_client().projects().zones().clusters().list(projectId=self.project, zone=zone)
        response = request.execute()
        if 'clusters' in response:
            return response["clusters"]

        return []

    def cleanup_k8s_jobs(self):
        for region in self.list_regions():
            for zone in self.list_zones(region):
                for cluster in self.get_clusters(zone):
                    cluster_name = cluster["name"]
                    self.log_dbg(f"Clean up of cluster {cluster_name} in zone {zone}")
                    client = self.kubectl_client(zone, cluster)
                    clean_jobs(self, client, cluster_name)
