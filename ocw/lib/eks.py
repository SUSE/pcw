import os
import json
import kubernetes
import boto3
from ocw.lib.provider import Provider
from ocw.lib.k8s import clean_jobs

TAG_IGNORE = 'pcw_ignore'


class EKS(Provider):
    __instances = {}
    default_region: str = 'eu-central-1'

    def __new__(cls, vault_namespace):
        if vault_namespace not in EKS.__instances:
            EKS.__instances[vault_namespace] = self = object.__new__(cls)
            self.__eks_client = {}
            self.__kubectl_client = {}
            self.__cluster_regions = None
            self.__aws_dir = None

        return EKS.__instances[vault_namespace]

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.create_credentials_file()

    def aws_dir(self):
        if self.__aws_dir is None:
            self.__aws_dir = os.path.expanduser("~/.aws")
        return self.__aws_dir

    def list_regions(self):
        if self.__cluster_regions is None:
            regions_query = self.cmd_exec(
                f"aws ec2 describe-regions --query 'Regions[].RegionName' --output json --region {EKS.default_region}")
            self.__cluster_regions = json.loads(regions_query.stdout)
        return self.__cluster_regions

    def create_credentials_file(self) -> None:
        creds_file = f"{self.aws_dir()}/credentials"

        if not os.path.exists(creds_file):
            if not os.path.exists(self.aws_dir()):
                os.mkdir(self.aws_dir())

            with open(creds_file, "w", encoding="utf8") as file_handle:
                file_handle.write("[default]\n")
                file_handle.write(f"aws_access_key_id={self.auth_json['access_key']}\n")
                file_handle.write(f"aws_secret_access_key={self.auth_json['secret_key']}\n")

        res = self.cmd_exec("aws sts get-caller-identity")
        if res.returncode != 0:
            raise RuntimeError("Invalid credentials, the credentials cannot be verified by"
                               f"'aws sts get-caller-identity' with the error: {res.stderr}")

    def eks_client(self, region: str) -> "boto3.session.Session.client":
        if region not in self.__eks_client:
            self.__eks_client[region] = boto3.client('eks',
                                                     aws_access_key_id=self.auth_json['access_key'],
                                                     aws_secret_access_key=self.auth_json['secret_key'],
                                                     region_name=region)
        return self.__eks_client[region]

    def kubectl_client(self, region: str, cluster_name: str):
        region_cluster = f"{region}/{cluster_name}"

        if region_cluster not in self.__kubectl_client:
            kubeconfig = f"~/.kube/eks_config_{region}_{cluster_name}"
            kubeconfig = os.path.expanduser(kubeconfig)

            res = self.cmd_exec(f"aws eks update-kubeconfig --region {region} --name {cluster_name} \
--kubeconfig {kubeconfig}")
            if res.returncode != 0:
                raise RuntimeError(f"Cannot get the kubeconfig for the cluster {cluster_name} on region {region}")

            kubernetes.config.load_kube_config(config_file=kubeconfig)
            self.__kubectl_client[region_cluster] = kubernetes.client.BatchV1Api()

        return self.__kubectl_client[region_cluster]

    def cleanup_k8s_jobs(self):
        for region in self.list_regions():
            self.log_dbg(f"Region {region}")
            clusters = self.eks_client(region).list_clusters()['clusters']
            for cluster_name in clusters:
                self.log_dbg(f"Clean up of cluster {cluster_name} in region {region}")
                client = self.kubectl_client(region, cluster_name)
                clean_jobs(self, client, cluster_name)
