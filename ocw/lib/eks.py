import os
import json
import time
from datetime import datetime, timedelta, timezone
import kubernetes
import boto3
from webui.PCWConfig import PCWConfig, ConfigFile
from ocw.lib.provider import Provider
from ocw.lib.k8s import clean_jobs

TAG_IGNORE = 'pcw_ignore'


class EKS(Provider):
    __instances = {}
    default_region: str = 'eu-central-1'
    __cluster_regions = []

    def __new__(cls, vault_namespace):
        if vault_namespace not in EKS.__instances:
            EKS.__instances[vault_namespace] = self = object.__new__(cls)
            self.__eks_client = {}
            self.__kubectl_client = {}
            self.__aws_dir = None

        return EKS.__instances[vault_namespace]

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.create_credentials_file()
        if len(EKS.__cluster_regions) == 0:
            if PCWConfig.has('clusters/ec2_regions'):
                EKS.__cluster_regions = ConfigFile().getList('clusters/ec2_regions')
            else:
                regions_query = self.cmd_exec(f"aws ec2 describe-regions --query 'Regions[].RegionName'\
                                               --output json --region {EKS.default_region}")
                EKS.__cluster_regions = json.loads(regions_query.stdout)

    def aws_dir(self):
        if self.__aws_dir is None:
            self.__aws_dir = os.path.expanduser("~/.aws")
        return self.__aws_dir

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

    def all_clusters(self) -> dict:
        clusters = {}
        for region in EKS.__cluster_regions:
            self.log_dbg("Checking clusters in {}", region)
            response = self.eks_client(region).list_clusters()
            if 'clusters' in response and len(response['clusters']) > 0:
                clusters[region] = []
                self.log_dbg("Found {} clusters in {}", len(response['clusters']), region)
                for cluster in response['clusters']:
                    cluster_description = self.eks_client(region).describe_cluster(name=cluster)
                    if 'cluster' not in cluster_description or 'tags' not in cluster_description['cluster']:
                        self.log_err("Unexpected cluster description: {}", cluster_description)
                    elif TAG_IGNORE not in cluster_description['cluster']['tags']:
                        clusters[region].append(cluster)
                if len(clusters[region]) == 0:
                    del clusters[region]
        return clusters

    def wait_for_empty_nodegroup_list(self, region: str, cluster_name: str, timeout_minutes: int = 20):
        if self.dry_run:
            self.log_info("Skip waiting due to dry-run mode")
            return None
        self.log_dbg("Waiting empty nodegroup list in {}", cluster_name)
        end = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        resp_nodegroup = self.eks_client(region).list_nodegroups(clusterName=cluster_name)

        while datetime.now(timezone.utc) < end and len(resp_nodegroup['nodegroups']) > 0:
            time.sleep(20)
            resp_nodegroup = self.eks_client(region).list_nodegroups(clusterName=cluster_name)
            if len(resp_nodegroup['nodegroups']) > 0:
                self.log_dbg("Still waiting for {} nodegroups to disappear", len(resp_nodegroup['nodegroups']))
        return None

    def delete_all_clusters(self) -> None:
        self.log_info("Deleting all clusters!")
        for region in self.__cluster_regions:
            response = self.eks_client(region).list_clusters()
            if len(response['clusters']):
                self.log_dbg("Found {} cluster(s) in {}", len(response['clusters']), region)
                for cluster in response['clusters']:
                    resp_nodegroup = self.eks_client(region).list_nodegroups(clusterName=cluster)
                    if len(resp_nodegroup['nodegroups']):
                        self.log_dbg("Found {} nodegroups for {}", len(resp_nodegroup['nodegroups']), cluster)
                        for nodegroup in resp_nodegroup['nodegroups']:
                            if self.dry_run:
                                self.log_info("Skipping {} nodegroup deletion due to dry-run mode", nodegroup)
                            else:
                                self.log_info("Deleting {}", nodegroup)
                                self.eks_client(region).delete_nodegroup(
                                    clusterName=cluster, nodegroupName=nodegroup)
                        self.wait_for_empty_nodegroup_list(region, cluster)
                    if self.dry_run:
                        self.log_info("Skipping {} cluster deletion due to dry-run mode", cluster)
                    else:
                        self.log_info("Finally deleting {} cluster", cluster)
                        self.eks_client(region).delete_cluster(name=cluster)

    def cleanup_k8s_jobs(self):
        self.log_info("Cleanup k8s jobs in EKS clusters")
        for region in self.__cluster_regions:
            self.log_dbg(f"Region {region}")
            clusters = self.eks_client(region).list_clusters()['clusters']
            for cluster_name in clusters:
                self.log_info(f"Cleanup k8s jobs in EKS cluster {cluster_name} in region {region}")
                client = self.kubectl_client(region, cluster_name)
                clean_jobs(self, client, cluster_name)
