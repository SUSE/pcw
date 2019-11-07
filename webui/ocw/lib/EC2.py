import boto3
import time
from .vault import EC2Credential
import logging


class EC2:
    __instances = dict()
    __key = None
    __secret = None
    __ec2_resource = dict()
    __ec2_client = dict()
    __credentials = None
    __logging = None

    def __new__(cls, vault_namespace):
        if vault_namespace not in EC2.__instances:
            EC2.__instances[vault_namespace] = object.__new__(cls)
            EC2.__instances[vault_namespace].__credentials = EC2Credential(vault_namespace)
            EC2.__instances[vault_namespace].__logging = logging.getLogger(__name__)

        EC2.__instances[vault_namespace].check_credentials()
        return EC2.__instances[vault_namespace]

    def check_credentials(self):
        if self.__credentials.isValid():
            self.__credentials.renew()
            self.__key = None
            self.__secret = None
            self.__ec2_resource = dict()
            self.__ec2_client = dict()

        self.__secret = self.__credentials.getData('secret_key')
        self.__key = self.__credentials.getData('access_key')

        for i in range(1, 60 * 5):
            try:
                self.list_regions()
                return True
            except Exception:
                self.__logging.info("check_credentials (attemp:%d) with key %s expiring at %s ",
                                    i, self.__key, self.__credentials.getAuthExpire())
                time.sleep(1)
        self.list_regions()

    def ec2_resource(self, region='eu-central-1'):
        if region not in self.__ec2_resource:
            self.__ec2_resource[region] = boto3.resource('ec2', aws_access_key_id=self.__key,
                                                         aws_secret_access_key=self.__secret,
                                                         region_name=region)
        return self.__ec2_resource[region]

    def ec2_client(self, region='eu-central-1'):
        if region not in self.__ec2_client:
            self.__ec2_client[region] = boto3.client('ec2', aws_access_key_id=self.__key,
                                                     aws_secret_access_key=self.__secret,
                                                     region_name=region)
        return self.__ec2_client[region]

    def list_instances(self, region='eu-central-1'):
        return [i for i in self.ec2_resource(region).instances.all()]

    def list_regions(self):
        regions_resp = self.ec2_client().describe_regions()
        regions = [region['RegionName'] for region in regions_resp['Regions']]
        return regions

    def delete_instance(self, instance_id):
        self.ec2_resource().instances.filter(InstanceIds=[instance_id]).terminate()
