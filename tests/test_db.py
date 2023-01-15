import json
from ocw.lib.db import ec2_to_local_instance, azure_to_local_instance, gce_to_json, tag_to_boolean, azure_to_json, \
    gce_to_local_instance, update_run
from ocw.models import ProviderChoice, StateChoice
from ocw.lib.gce import GCE
from webui.settings import PCWConfig
from tests.generators import ec2_instance_mock, azure_instance_mock, gce_instance_mock
from faker import Faker
from datetime import datetime
import dateutil.parser
import pytest

fake = Faker()


@pytest.fixture
def update_run_patch(monkeypatch):

    class Mock_Scheduler:

        def get_job(self, val1):
            return True

    monkeypatch.setattr(PCWConfig, 'get_namespaces_for', lambda namespace: ['namespace1'])
    monkeypatch.setattr(PCWConfig, 'get_providers_for', lambda namespace, region: ['provider1'])
    monkeypatch.setattr('ocw.apps.getScheduler', lambda namespace: Mock_Scheduler())


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

    assert result['type'] == GCE.url_to_name(test_instance['machineType'])
    assert result['launch_time'] == str(test_instance['creationTimestamp'])
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


def test_gce_to_local_instance():
    test_instance = gce_instance_mock()
    test_vault = fake.uuid4()
    result = gce_to_local_instance(test_instance, test_vault)

    test_csp_info = gce_to_json(test_instance)
    assert result.provider == ProviderChoice.GCE
    assert result.vault_namespace == test_vault
    assert str(result.first_seen) == test_csp_info.get('launch_time')


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


def test__update_run(update_run_patch, monkeypatch):

    call_stack = []

    def mocked__update_provider(arg1, arg2):
        call_stack.append('_update_provider')

    def mocked_auto_delete_instances():
        call_stack.append('auto_delete_instances')

    def mocked_send_leftover_notification():
        call_stack.append('send_leftover_notification')

    monkeypatch.setattr('ocw.lib.db._update_provider', mocked__update_provider)
    monkeypatch.setattr('ocw.lib.db.auto_delete_instances', mocked_auto_delete_instances)
    monkeypatch.setattr('ocw.lib.db.send_leftover_notification', mocked_send_leftover_notification)

    update_run()

    assert call_stack == ['_update_provider', 'auto_delete_instances', 'send_leftover_notification']


def test__update_run_update_provider_throw_exception(update_run_patch, monkeypatch):

    call_stack = []

    def mocked__update_provider(arg1, arg2):
        call_stack.append('_update_provider')
        raise Exception

    def mocked_auto_delete_instances():
        call_stack.append('auto_delete_instances')

    def mocked_send_leftover_notification():
        call_stack.append('send_leftover_notification')

    def mocked_send_mail(arg1, arg2):
        call_stack.append('send_mail')

    monkeypatch.setattr('ocw.lib.db._update_provider', mocked__update_provider)
    monkeypatch.setattr('ocw.lib.db.auto_delete_instances', mocked_auto_delete_instances)
    monkeypatch.setattr('ocw.lib.db.send_leftover_notification', mocked_send_leftover_notification)
    monkeypatch.setattr('ocw.lib.db.send_mail', mocked_send_mail)

    update_run()

    assert call_stack == ['_update_provider', 'send_mail', 'auto_delete_instances', 'send_leftover_notification']
