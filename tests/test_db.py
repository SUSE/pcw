from os.path import basename
from ocw.lib.db import update_run, ec2_extract_data, gce_extract_data, azure_extract_data, delete_instance, reset_stale_deleting
from webui.PCWConfig import PCWConfig
from faker import Faker
from tests.generators import ec2_csp_instance_mock, gce_instance_mock, azure_instance_mock
from ocw.models import ProviderChoice, StateChoice, Instance, CspInfo
from ocw.lib.gce import GCE
from ocw.lib.azure import Azure
from ocw.lib.ec2 import EC2
import json
from django.db import transaction
import pytest
import dateutil.parser as dateparser
from datetime import datetime, timezone, timedelta

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
    def __init__(self, provider, state=None, ttl=None, first_seen=None):
        self.state = state if state is not None else None
        self.instance_id = fake.uuid4()
        self.region = None
        self.save_called = False
        self.provider = provider
        self.namespace = fake.uuid4()
        self.ttl = ttl if ttl is not None else timedelta(seconds=3600)  # Default TTL 1 hour
        self.first_seen = first_seen if first_seen else datetime.now(tz=timezone.utc)
        self.last_seen = self.first_seen  # For all_time_fields()
        self.age = timedelta(seconds=0)  # Placeholder

    def save(self, update_fields=None):
        self.save_called = True

    def all_time_fields(self):
        return f"first_seen={self.first_seen}, ttl={self.ttl.total_seconds()}s"


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
    monkeypatch.setattr(Azure, '__new__', lambda cls, namespace: AzureMock())
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
    assert rez['region'] == basename(csp_instance['zone'])
    assert rez['provider'] == ProviderChoice.GCE
    assert rez['type'] == basename(csp_instance['machineType'])
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

    def mocked_reset_stale_deleting():
        call_stack.append('reset_stale_deleting')

    def mocked_auto_delete_instances():
        call_stack.append('auto_delete_instances')

    monkeypatch.setattr('ocw.lib.db._update_provider', mocked__update_provider)
    monkeypatch.setattr('ocw.lib.db.reset_stale_deleting', mocked_reset_stale_deleting)
    monkeypatch.setattr('ocw.lib.db.auto_delete_instances', mocked_auto_delete_instances)

    update_run()

    assert call_stack == ['_update_provider', 'reset_stale_deleting', 'auto_delete_instances']


@pytest.mark.django_db
def test_reset_stale_deleting(monkeypatch):
    """Test reset_stale_deleting resets stale DELETING instances."""
    # Setup
    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    namespace = "test_namespace"
    default_ttl = timedelta(minutes=15).total_seconds()
    threshold = timedelta(hours=2).total_seconds()

    # Mock PCWConfig
    monkeypatch.setattr(PCWConfig, 'get_namespaces_for', lambda x: [namespace])
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda feature, prop, ns: threshold)

    # Test cases
    test_cases = [
        # Case 1: Stale (3h > 2h)
        {
            'instance_id': "test-instance-stale",
            'state': StateChoice.DELETING,
            'deleting_since': now - timedelta(hours=3),  # 3 hours ago
            'should_reset': True,
            'desc': "Stale (3h > 2h)",
            'pcw_ignore': False
        },
        # Case 2: Not Stale (1h < 2h)
        {
            'instance_id': "test-instance-not-stale",
            'state': StateChoice.DELETING,
            'deleting_since': now - timedelta(hours=1),  # 1 hour ago
            'should_reset': False,
            'desc': "Not Stale (1h < 2h)",
            'pcw_ignore': False
        },
        # Case 3: Non-Deleting (ACTIVE)
        {
            'instance_id': "test-instance-active",
            'state': StateChoice.ACTIVE,
            'deleting_since': now - timedelta(hours=3),  # Shouldn’t matter
            'should_reset': False,
            'desc': "Non-Deleting (ACTIVE)",
            'pcw_ignore': False
        },
        # Case 4: Edge (2h = 2h)
        {
            'instance_id': "test-instance-edge",
            'state': StateChoice.DELETING,
            'deleting_since': now - timedelta(hours=2),  # Exactly 2 hours ago
            'should_reset': True,
            'desc': "Edge (2h = 2h)",
            'pcw_ignore': False
        },
        # Case 5: Edge (1h 59m < 2h)
        {
            'instance_id': "test-instance-edge-2",
            'state': StateChoice.DELETING,
            'deleting_since': now - timedelta(hours=1) - timedelta(minutes=59),  # Exactly 2 hours ago
            'should_reset': False,
            'desc': "Edge (1h 59m < 2h)",
            'pcw_ignore': False
        },
        # Case 6: Stale (3h > 2h) but pcw_ignore tag is True
        {
            'instance_id': "test-instance-stale-but-ignored",
            'state': StateChoice.DELETING,
            'deleting_since': now - timedelta(hours=3),  # 3 hours ago
            'should_reset': False,
            'desc': "Stale (3h > 2h)",
            'pcw_ignore': True
        },
    ]

    # Cleanup database before test
    Instance.objects.all().delete()
    CspInfo.objects.all().delete()

    # Create test instances
    instances = []
    for case in test_cases:
        with transaction.atomic():
            instance = Instance(
                provider=ProviderChoice.AZURE,
                namespace=namespace,
                instance_id=case['instance_id'],
                state=case['state'],
                ttl=timedelta(seconds=default_ttl),
                first_seen=now - timedelta(days=1),
                deleting_since=case['deleting_since'],
                last_seen=case['deleting_since'] or now - timedelta(days=1),
                age=timedelta(seconds=0),
                region="test-region",
                active=case['state'] == StateChoice.ACTIVE
            )
            instance.save()
            tags = {'openqa_ttl': str(default_ttl)}
            if case['pcw_ignore']:
                tags[Instance.TAG_IGNORE] = "True"

            CspInfo.objects.create(
                instance=instance,
                tags=json.dumps(tags),
                type="test_type"
            )

            instance.set_alive() # required so that ignore is recomputed
            instance.save()  # required to save the ignore field
            instances.append(instance)

    # Run the function
    reset_stale_deleting()

    # Check results
    for instance, case in zip(instances, test_cases):
        instance.refresh_from_db()
        time_in_deleting = (
            (now - instance.deleting_since).total_seconds()
            if instance.deleting_since
            else float('inf')
        )
        print(f"\nCase: {case['desc']}")
        print(f"state: {instance.state}")
        print(f"deleting_since: {instance.deleting_since}")
        print(f"time_in_deleting: {time_in_deleting}s")
        print(f"threshold: {threshold}s")
        print(f"pcw_ignore expected: {case['pcw_ignore']}, actual: {instance.ignore}")
        print(f"should_reset: {case['should_reset']}")

        if case['should_reset']:
            assert instance.state == StateChoice.ACTIVE, f"State should reset to ACTIVE for {case['desc']}"
            assert instance.deleting_since is None, f"deleting_since should be cleared for {case['desc']}"
        else:
            assert instance.state == case['state'], f"State should remain {case['state']} for {case['desc']}"
            assert instance.deleting_since == case['deleting_since'], f"deleting_since should remain unchanged for {case['desc']}"


def test_update_run_update_provider_throw_exception(update_run_patch, monkeypatch):

    call_stack = []

    def mocked__update_provider(arg1, arg2, arg3):
        call_stack.append('_update_provider')
        raise Exception

    def mocked_reset_stale_deleting():
        call_stack.append('reset_stale_deleting')

    def mocked_auto_delete_instances():
        call_stack.append('auto_delete_instances')

    def mocked_send_mail(arg1, arg2):
        call_stack.append('send_mail')

    monkeypatch.setattr('ocw.lib.db._update_provider', mocked__update_provider)
    monkeypatch.setattr('ocw.lib.db.reset_stale_deleting', mocked_reset_stale_deleting)
    monkeypatch.setattr('ocw.lib.db.auto_delete_instances', mocked_auto_delete_instances)
    monkeypatch.setattr('ocw.lib.db.send_mail', mocked_send_mail)

    update_run()

    assert call_stack == ['_update_provider', 'send_mail', 'reset_stale_deleting', 'auto_delete_instances']


def test_delete_instances_azure(monkeypatch):
    monkeypatch.setattr(Azure, '__new__', lambda cls, namespace: AzureMock())

    instance = InstanceMock(ProviderChoice.AZURE)

    delete_instance(instance)

    assert instance.save_called
    assert instance.state == StateChoice.DELETING


def test_delete_instances_ec2(monkeypatch):
    monkeypatch.setattr(EC2, '__new__', lambda cls, namespace: EC2Mock())

    instance = InstanceMock(ProviderChoice.EC2)

    delete_instance(instance)

    assert instance.save_called
    assert instance.state == StateChoice.DELETING


def test_delete_instances_gce(monkeypatch):
    monkeypatch.setattr(GCE, '__new__', lambda cls, namespace: GCEMock())

    instance = InstanceMock(ProviderChoice.GCE)

    delete_instance(instance)

    assert instance.save_called
    assert instance.state == StateChoice.DELETING
