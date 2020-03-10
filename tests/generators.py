from faker import Faker
from datetime import datetime
from datetime import timedelta
from datetime import timezone

fake = Faker()
min_image_age_hours = 7
max_images_per_flavor = 1
max_image_age_hours = 20


class MockProperties:
    def __init__(self, last_modified):
        self.last_modified = last_modified


class MockImage:
    def __init__(self, name, last_modified):
        self.name = name
        self.properties = MockProperties(last_modified)


def mock_cfgGet(self, section, field):
    if field == 'min-image-age-hours':
        return min_image_age_hours
    elif field == 'max-images-per-flavor':
        return max_images_per_flavor
    elif field == 'max-image-age-hours':
        return max_image_age_hours


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


def generate_mocked_images_older_than(hours):
    last_modified = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd', last_modified),
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd', last_modified),
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.7.vhd', last_modified),
            MockImage('SLES15-SP2-BYOS.x86_64-0.9.3-Azure-Build2.36.vhd', last_modified),
            MockImage('SLES15-SP2-BYOS.x86_64-0.9.6-Azure-Build1.3.vhd', last_modified),
            MockImage('SLES15-SP2-BYOS.x86_64-0.9.6-Azure-Build1.9.vhd', last_modified)
            ]
