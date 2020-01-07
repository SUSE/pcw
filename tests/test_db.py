import pytest
from ocw.lib.db import ec2_to_json
from faker import Faker

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
        self.image_id = fake.uuid4()
        self.instance_lifecycle = fake.uuid4()
        self.instance_type = fake.uuid4()
        self.kernel_id = fake.uuid4()
        self.launch_time = fake.future_date()
        self.public_ip_address = fake.uuid4()
        self.security_groups = [{'GroupName': fake.uuid4()}, {'GroupName': fake.uuid4()}]
        self.sriov_net_support = fake.uuid4()
        self.tags = [{'Key': fake.uuid4(), 'Value': fake.uuid4()}]
        self.state_reason = {'Message': fake.uuid4()}
        self.image = ec2_image_mock()


def test_ec2_to_json():
    test_instance = ec2_instance_mock()
    test_instance.state_reason = None
    test_instance.image = None
    result = ec2_to_json(test_instance)
    assert result['state'] == test_instance.state['Name']
    assert result['image_id'] == test_instance.image_id
    assert result['instance_lifecycle'] == test_instance.instance_lifecycle
    assert result['instance_type'] == test_instance.instance_type
    assert result['kernel_id'] == test_instance.kernel_id
    assert result['launch_time'] == test_instance.launch_time.isoformat()
    assert result['public_ip_address'] == test_instance.public_ip_address
    assert len(result['security_groups']) == len(test_instance.security_groups)
    # TODO compare values of 'security_groups'
    assert result['sriov_net_support'] == test_instance.sriov_net_support
    for t in test_instance.tags:
        assert result['tags'][t['Key']] == t['Value']
    assert 'state_reason' not in result
    assert 'image' not in result


def test_ec2_to_json_state_reason():
    test_instance = ec2_instance_mock()
    result = ec2_to_json(test_instance)
    assert result['state_reason'] == test_instance.state_reason['Message']


def test_ec2_to_json_image_without_meta():
    test_instance = ec2_instance_mock()
    test_instance.image.meta.data = None
    result = ec2_to_json(test_instance)
    assert result['image']['image_id'] == test_instance.image.image_id
    assert 'name' not in result['image']


def test_ec2_to_json_image_with_meta():
    test_instance = ec2_instance_mock()
    result = ec2_to_json(test_instance)
    assert result['image']['name'] == test_instance.image.name
