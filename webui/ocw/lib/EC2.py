from .vault import EC2Credential


class EC2:
    __instance = None
    __credentials = None

    def __new__(cls):
        if EC2.__instance is None:
            EC2.__instance = object.__new__(cls)
            EC2.__instance.__credentials = EC2Credential()
        return EC2.__instance

    def list_instances(self, region='eu-central-1'):
        return self.__credentials.ec2_resource(region).instances.all()

    def list_regions(self):
        return self.__credentials.list_regions()

    def delete_instance(self, instance_id):
        self.__crdentials.ec2_resource().instances.filter(InstanceIds=[instance_id]).terminate()
