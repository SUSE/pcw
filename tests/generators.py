from faker import Faker
from datetime import datetime

fake = Faker()


class ec2_meta_mock:
    def __init__(self):
        self.data = fake.uuid4()


class ec2_image_mock:
    def __init__(self):
        self.image_id = fake.uuid4()
        self.meta = ec2_meta_mock()
        self.name = fake.uuid4()


class ec2_instance_mock:
    def __init__(self):
        self.state = {'Name': fake.uuid4()}
        self.instance_id = fake.uuid4()
        self.image_id = fake.uuid4()
        self.instance_lifecycle = fake.uuid4()
        self.instance_type = fake.uuid4()
        self.kernel_id = fake.uuid4()
        self.launch_time = datetime.now()
        self.public_ip_address = fake.uuid4()
        self.security_groups = [{'GroupName': fake.uuid4()}, {'GroupName': fake.uuid4()}]
        self.sriov_net_support = fake.uuid4()
        self.tags = [{'Key': fake.uuid4(), 'Value': fake.uuid4()}]
        self.state_reason = {'Message': fake.uuid4()}
        self.image = ec2_image_mock()


class azure_instance_mock:
    def __init__(self):
        self.tags = fake.uuid4()
        self.name = fake.uuid4()
        self.id = fake.uuid4()
        self.type = fake.uuid4()
        self.location = fake.uuid4()


def gce_instance_mock():
    return {
        'name': fake.uuid4(),
        'id': fake.uuid4(),
        'machineType': fake.uuid4() + '/qq',
        'zone': fake.uuid4() + '/qq',
        'status': fake.uuid4(),
        'creationTimestamp': datetime.now(),
        'metadata': fake.uuid4(),
        'tags': {'sshKeys': fake.uuid4()}
    }
