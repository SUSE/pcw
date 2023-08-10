import os
import kubernetes
from ocw.lib.provider import Provider
from ocw.lib.k8s import clean_jobs, clean_namespaces
from webui.PCWConfig import PCWConfig


class AKS(Provider):
    __instances = {}
    default_region: str = 'eu-central-1'

    def __new__(cls, vault_namespace):
        if vault_namespace not in AKS.__instances:
            AKS.__instances[vault_namespace] = self = object.__new__(cls)
            self.__kubectl_client = {}
        return AKS.__instances[vault_namespace]

    def subscription(self) -> str:
        return self.get_data('subscription_id')

    def kubectl_client(self, resource_group: str, cluster_name: str):
        if cluster_name not in self.__kubectl_client:
            kubeconfig = f"~/.kube/aks_config_{self.subscription()}_{resource_group}_{cluster_name}"
            kubeconfig = os.path.expanduser(kubeconfig)

            res = self.cmd_exec(f"az login --service-principal -u {self.get_data('client_id')} "
                                f"-p {self.get_data('client_secret')} --tenant {self.get_data('tenant_id')}")
            if res.returncode != 0:
                raise RuntimeError(f"Cannot login to azure : {res.stderr}")

            res = self.cmd_exec(f"az aks get-credentials --resource-group {resource_group} "
                                f"--name {cluster_name} --file {kubeconfig}")
            if res.returncode != 0:
                raise RuntimeError(f"Cannot get the kubeconfig for the cluster {cluster_name} "
                                   f"for resource-group {resource_group} : {res.stderr}")

            kubernetes.config.load_kube_config(config_file=kubeconfig)
            self.__kubectl_client[cluster_name] = kubernetes.client

        return self.__kubectl_client[cluster_name]

    def cleanup_k8s_jobs(self):
        clusters = PCWConfig.get_k8s_clusters_for_provider(self._namespace, "azure")
        self.log_info(f"Cleanup jobs in AKS clusters. {len(clusters)}  will be queried ")
        for cluster in clusters:
            self.log_info(f"Cleaning jobs in AKS cluster {cluster['cluster_name']}")
            client = self.kubectl_client(cluster["resource_group"], cluster["cluster_name"]).BatchV1Api()
            clean_jobs(self, client, cluster["cluster_name"])

    def cleanup_k8s_namespaces(self):
        clusters = PCWConfig.get_k8s_clusters_for_provider(self._namespace, "azure")
        self.log_info(f"Cleanup namespaces in AKS clusters. {len(clusters)}  will be queried ")
        for cluster in clusters:
            self.log_info(f"Cleaning namespaces in AKS cluster {cluster['cluster_name']}")
            client = self.kubectl_client(cluster["resource_group"], cluster["cluster_name"]).CoreV1Api()
            clean_namespaces(self, client)
