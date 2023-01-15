from faker import Faker
from datetime import datetime

fake = Faker()
max_age_hours = 7
azure_storage_resourcegroup = 'openqa'
ec2_max_age_days = 1


def mock_get_feature_property(feature: str, property: str, namespace: str = None):
    if property == 'max-age-hours':
        return max_age_hours
    elif property == 'azure-storage-resourcegroup':
        return azure_storage_resourcegroup
    elif property == 'ec2-max-age-days':
        return ec2_max_age_days


def ec2_tags_mock(tags={fake.uuid4(): fake.uuid4()}):
    return [{'Key': key, 'Value': tags[key]} for key in tags]


class ec2_instance_mock:
    def __init__(self, **kwargs):
        self.instance_id = fake.uuid4()
        self.instance_type = fake.uuid4()
        self.launch_time = datetime.now()
        self.tags = ec2_tags_mock(**kwargs)


class azure_instance_mock:
    def __init__(self):
        self.tags = fake.uuid4()
        self.name = fake.uuid4()
        self.location = fake.uuid4()


def gce_instance_mock():
    return {
        'id': fake.uuid4(),
        'machineType': fake.uuid4() + '/qq',
        'zone': fake.uuid4() + '/qq',
        'creationTimestamp': datetime.now(),
        'metadata': fake.uuid4(),
        'tags': {'sshKeys': fake.uuid4()}
    }
