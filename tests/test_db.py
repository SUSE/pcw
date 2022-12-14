import json
from ocw.lib.db import ec2_to_local_instance
from ocw.lib.db import ec2_to_json
from ocw.lib.db import azure_to_json
from ocw.lib.db import azure_to_local_instance
from ocw.lib.db import gce_to_json
from ocw.lib.db import tag_to_boolean
from ocw.models import ProviderChoice
from ocw.models import StateChoice
from ocw.lib.gce import GCE
from tests.generators import ec2_instance_mock
from tests.generators import azure_instance_mock
from tests.generators import gce_instance_mock
from faker import Faker
from datetime import datetime
import dateutil.parser

fake = Faker()


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


def test_ec2_to_local_instance():
    test_instance = ec2_instance_mock()
    test_vault_namespace = fake.uuid4()
    test_region = fake.uuid4()

    result = ec2_to_local_instance(test_instance, test_vault_namespace, test_region)

    assert result.provider == ProviderChoice.EC2
    assert result.vault_namespace == test_vault_namespace
    assert result.first_seen == test_instance.launch_time
    assert result.instance_id == test_instance.instance_id
    assert result.state == StateChoice.ACTIVE
    assert result.region == test_region
    json.loads(result.csp_info)


def test_azure_to_json():
    test_instance = azure_instance_mock()
    result = azure_to_json(test_instance)

    assert result['tags'] == test_instance.tags
    assert result['name'] == test_instance.name
    assert result['id'] == test_instance.id
    assert result['type'] == test_instance.type
    assert result['location'] == test_instance.location
    assert 'launch_time' not in result


def test_azure_to_json_launch_time():
    test_instance = azure_instance_mock()
    test_time = datetime.now()
    test_instance.tags = {'openqa_created_date': test_time}
    result = azure_to_json(test_instance)
    assert result['launch_time'] == test_time


def test_azure_to_local_instance():
    test_instance = azure_instance_mock()
    test_instance.tags = {'openqa_created_date': str(datetime.now())}
    test_vault_namespace = fake.uuid4()
    result = azure_to_local_instance(test_instance, test_vault_namespace)

    assert result.provider == ProviderChoice.AZURE
    assert result.vault_namespace == test_vault_namespace
    assert result.first_seen == dateutil.parser.parse(test_instance.tags.get('openqa_created_date'))
    assert result.instance_id == test_instance.name
    assert result.region == test_instance.location
    json.loads(result.csp_info)


def test_gce_to_json():
    test_instance = gce_instance_mock()
    result = gce_to_json(test_instance)

    assert result['name'] == test_instance['name']
    assert result['id'] == test_instance['id']
    assert result['machineType'] == GCE.url_to_name(test_instance['machineType'])
    assert result['zone'] == GCE.url_to_name(test_instance['zone'])
    assert result['status'] == test_instance['status']
    assert result['launch_time'] == test_instance['creationTimestamp']
    assert result['creation_time'] == test_instance['creationTimestamp']
    assert len(result['tags']) == 0
    assert 'sshKeys' not in result['tags']


def test_gce_to_json_metadata_items():
    test_instance = gce_instance_mock()
    test_items = [{'key': fake.uuid4(), 'value': fake.uuid4()}, {'key': fake.uuid4(), 'value': fake.uuid4()}]
    test_instance['metadata'] = {'items': test_items}
    result = gce_to_json(test_instance)

    assert len(result['tags']) == 2


def test_gce_to_json_launch_time():
    test_instance = gce_instance_mock()
    test_time = datetime.now()
    test_items = [{'key': 'openqa_created_date', 'value': test_time}]
    test_instance['metadata'] = {'items': test_items}
    result = gce_to_json(test_instance)

    assert result['launch_time'] == test_time


def test_tag_to_boolean():
    tag_name = 'test'
    csp_info = {}
    assert tag_to_boolean(tag_name, csp_info) is False
    csp_info = {'tags': {}}
    assert tag_to_boolean(tag_name, csp_info) is False
    csp_info = {'tags': {'test': None}}
    assert tag_to_boolean(tag_name, csp_info) is False
    csp_info = {'tags': {'test': False}}
    assert tag_to_boolean(tag_name, csp_info) is False
    csp_info = {'tags': {'test': '1'}}
    assert tag_to_boolean(tag_name, csp_info) is True
