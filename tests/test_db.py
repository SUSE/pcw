from ocw.lib.db import update_run, ec2_extract_data, gce_extract_data, azure_extract_data, delete_instance
from webui.PCWConfig import PCWConfig
from faker import Faker
from tests.generators import ec2_csp_instance_mock, gce_instance_mock, azure_instance_mock
from ocw.models import ProviderChoice, StateChoice
from ocw.lib.gce import GCE
from ocw.lib.azure import Azure
from ocw.lib.EC2 import EC2
import pytest
import dateutil.parser as dateparser
from datetime import datetime, timezone

fake = Faker()


class AzureMock:
    def get_vm_types_in_resource_group(self, name):
        return name

    def delete_resource(self, id):
        pass


class EC2Mock:
    def delete_instance(self, region, instance_id):
        pass


class GCEMock:
    def delete_instance(self, instance_id, region):
        pass


class InstanceMock:
    def __init__(self, provider):
        self.state = None
        self.instance_id = fake.uuid4()
        self.region = None
        self.save_called = False
        self.provider = provider
        self.vault_namespace = fake.uuid4()

    def save(self):
        self.save_called = True


@pytest.fixture
def update_run_patch(monkeypatch):

    class Mock_Scheduler:

        def get_job(self, val1):
            return True

    monkeypatch.setattr(PCWConfig, 'get_namespaces_for', lambda namespace: ['namespace1'])
    monkeypatch.setattr(PCWConfig, 'get_providers_for', lambda namespace, region: ['provider1'])
    monkeypatch.setattr('ocw.apps.getScheduler', lambda namespace: Mock_Scheduler())


@pytest.fixture
def extract_data():
    return {
        'namespace': fake.uuid4(),
        'default_ttl': 1111,
        'region': fake.uuid4()
    }


@pytest.fixture
def azure_fixture(monkeypatch, extract_data):
    monkeypatch.setattr(Azure, '__new__', lambda cls, vault_namespace: AzureMock())
    return extract_data


def test_ec2_extract_data(extract_data):

    csp_instance = ec2_csp_instance_mock("random")
    rez = ec2_extract_data(csp_instance, extract_data['namespace'],
                           extract_data['region'], extract_data['default_ttl'])

    assert csp_instance.tags[0]['Key'] in rez['tags']
    assert rez['id'] == csp_instance.instance_id
    assert rez['first_seen'] == csp_instance.launch_time
    assert rez['namespace'] == extract_data['namespace']
    assert rez['region'] == extract_data['region']
    assert rez['provider'] == ProviderChoice.EC2
    assert rez['type'] == csp_instance.instance_type
    assert rez['default_ttl'] == extract_data['default_ttl']


def test_ec2_extract_data_empty_tags(extract_data):
    csp_instance = ec2_csp_instance_mock("empty")
    rez = ec2_extract_data(csp_instance, extract_data['namespace'],
                           extract_data['region'], extract_data['default_ttl'])
    assert rez['tags'] == {}


def test_gce_extract_data(extract_data):

    csp_instance = gce_instance_mock("random_with_sshkey")
    rez = gce_extract_data(csp_instance, extract_data['namespace'], extract_data['default_ttl'])

    assert csp_instance['metadata']['items'][0]['key'] in rez['tags']
    assert 'sshKeys' not in rez['tags']
    assert rez['id'] == csp_instance['id']
    assert rez['first_seen'] == csp_instance['creationTimestamp']
    assert rez['namespace'] == extract_data['namespace']
    assert rez['region'] == GCE.url_to_name(csp_instance['zone'])
    assert rez['provider'] == ProviderChoice.GCE
    assert rez['type'] == GCE.url_to_name(csp_instance['machineType'])
    assert rez['default_ttl'] == extract_data['default_ttl']


def test_gce_extract_data_items_empty(extract_data):

    csp_instance = gce_instance_mock("empty_items")
    rez = gce_extract_data(csp_instance, extract_data['namespace'], extract_data['default_ttl'])

    assert len(rez['tags']) == 0
    assert rez['first_seen'] == csp_instance['creationTimestamp']


def test_gce_extract_data_creation_date_tag(extract_data):
    csp_instance = gce_instance_mock("creation_date_tag")
    rez = gce_extract_data(csp_instance, extract_data['namespace'], extract_data['default_ttl'])

    assert len(rez['tags']) == 1
    assert rez['first_seen'] == dateparser.parse(csp_instance['metadata']['items'][0]['value'])


def test_gce_extract_data_metadata_empty(extract_data):

    csp_instance = gce_instance_mock("empty_metadata")
    rez = gce_extract_data(csp_instance, extract_data['namespace'], extract_data['default_ttl'])

    assert len(rez['tags']) == 0
    assert rez['first_seen'] == csp_instance['creationTimestamp']


def test_azure_extract_data(azure_fixture):

    csp_instance = azure_instance_mock("openqa_created_date")
    rez = azure_extract_data(csp_instance, azure_fixture['namespace'], azure_fixture['default_ttl'])

    assert csp_instance.tags == rez['tags']
    assert rez['id'] == csp_instance.name
    assert rez['first_seen'] == dateparser.parse(csp_instance.tags.get('openqa_created_date'))
    assert rez['namespace'] == azure_fixture['namespace']
    assert rez['region'] == csp_instance.location
    assert rez['provider'] == ProviderChoice.AZURE
    assert rez['type'] == csp_instance.name
    assert rez['default_ttl'] == azure_fixture['default_ttl']


def test_azure_extract_data_no_created_date(azure_fixture):

    csp_instance = azure_instance_mock("random")
    rez = azure_extract_data(csp_instance, azure_fixture['namespace'], azure_fixture['default_ttl'])

    assert (datetime.now(timezone.utc) - rez['first_seen']).days == 0


def test_azure_extract_data_no_tags(azure_fixture):

    csp_instance = azure_instance_mock("no_tags")
    rez = azure_extract_data(csp_instance, azure_fixture['namespace'], azure_fixture['default_ttl'])

    assert rez['tags'] == {}


def test_update_run(update_run_patch, monkeypatch):

    call_stack = []

    def mocked__update_provider(arg1, arg2, arg3):
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


def test_update_run_update_provider_throw_exception(update_run_patch, monkeypatch):

    call_stack = []

    def mocked__update_provider(arg1, arg2, arg3):
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


def test_delete_instances_azure(monkeypatch):
    monkeypatch.setattr(Azure, '__new__', lambda cls, vault_namespace: AzureMock())

    instance = InstanceMock(ProviderChoice.AZURE)

    delete_instance(instance)

    assert instance.save_called
    assert instance.state == StateChoice.DELETING


def test_delete_instances_ec2(monkeypatch):
    monkeypatch.setattr(EC2, '__new__', lambda cls, vault_namespace: EC2Mock())

    instance = InstanceMock(ProviderChoice.EC2)

    delete_instance(instance)

    assert instance.save_called
    assert instance.state == StateChoice.DELETING


def test_delete_instances_gce(monkeypatch):
    monkeypatch.setattr(GCE, '__new__', lambda cls, vault_namespace: GCEMock())

    instance = InstanceMock(ProviderChoice.GCE)

    delete_instance(instance)

    assert instance.save_called
    assert instance.state == StateChoice.DELETING
