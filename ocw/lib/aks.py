import os
import kubernetes
from azure.identity import ClientSecretCredential
from azure.mgmt.containerservice import ContainerServiceClient
from azure.mgmt.resource import ResourceManagementClient
from ocw.lib.provider import Provider
from ocw.lib.k8s import clean_jobs
from webui.PCWConfig import PCWConfig


class AKS(Provider):
    __instances = {}
    default_region: str = 'eu-central-1'

    def __new__(cls, vault_namespace):
        if vault_namespace not in AKS.__instances:
            AKS.__instances[vault_namespace] = self = object.__new__(cls)
            self.__container_mgmt_client = None
            self.__resource_mgmt_client = None
            self.__sp_credentials = None
            self.__kubectl_client = {}
        return AKS.__instances[vault_namespace]

    def subscription(self) -> str:
        return self.get_data('subscription_id')

    def sp_credentials(self):
        if self.__sp_credentials is None:
            self.__sp_credentials = ClientSecretCredential(client_id=self.get_data(
                'client_id'), client_secret=self.get_data('client_secret'), tenant_id=self.get_data('tenant_id'))
        return self.__sp_credentials

    def container_mgmt_client(self):
        if self.__container_mgmt_client is None:
            self.__container_mgmt_client = ContainerServiceClient(
                self.sp_credentials(), self.subscription())
        return self.__container_mgmt_client

    def resource_mgmt_client(self):
        if self.__resource_mgmt_client is None:
            self.__resoure_mgmt_client = ResourceManagementClient(
                self.sp_credentials(), self.subscription())
        return self.__resoure_mgmt_client

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
            self.__kubectl_client[cluster_name] = kubernetes.client.BatchV1Api()

        return self.__kubectl_client[cluster_name]

    def cleanup_k8s_jobs(self):
        clusters = PCWConfig.get_k8s_clusters_for_provider(self._namespace, "azure")
        for cluster in clusters:
            client = self.kubectl_client(cluster["resource_group"], cluster["cluster_name"])
            clean_jobs(self, client, cluster["cluster_name"])
