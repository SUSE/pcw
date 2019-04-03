import boto3
import time
from .vault import EC2Credential


class EC2:
    __instance = None
    __resource_by_region = dict()
    __client_by_region = dict()
    __credentials = None

    def __new__(cls):
        if EC2.__instance is None:
            EC2.__instance = object.__new__(cls)
            EC2.__instance.__credentials = EC2Credential()

        EC2.__instance.check_credentials()
        return EC2.__instance

    def check_credentials(self):
        for i in range(1, 60 * 5):
            try:
                self.list_regions()
                return True
            except Exception as e:
                print('CredentialsError (attemp:{}) - {}'.format(i, str(e)))
                time.sleep(1)
        raise Exception("Invalid EC2 credentials")

    def get_resource_region(self, region='eu-central-1'):
        if region not in self.__resource_by_region or self.__credentials.isExpired():
            key, secret = self.getKey_and_secret()
            self.__resource_by_region[region] = boto3.resource('ec2', aws_access_key_id=key,
                                                             aws_secret_access_key=secret,
                                                             region_name=region)
        return self.__resource_by_region[region]

    def get_client_region(self, region='eu-central-1'):
        if region not in self.__client_by_region or self.__credentials.isExpired():
            key, secret = self.getKey_and_secret()
            self.__client_by_region[region] = boto3.client('ec2', aws_access_key_id=key,
                                                         aws_secret_access_key=secret,
                                                         region_name=region)
        return self.__client_by_region[region]

    def getKey_and_secret(self):
        return self.__credentials.getData('access_key'), self.__credentials.getData('secret_key')

    def list_instances(self, region='eu-central-1'):
        return self.get_resource_region(region).instances.all()

    def list_regions(self):
        regions_resp = self.get_client_region().describe_regions()
        self.__client_by_region = [region['RegionName'] for region in regions_resp['Regions']]
        return self.__client_by_region

    def delete_instance(self, instance_id):
        self.get_resource_region().instances.filter(InstanceIds=[instance_id]).terminate()
