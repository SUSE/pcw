import os
import kubernetes
from ocw.lib.EC2 import EC2, Provider
from webui.PCWConfig import PCWConfig
from tests.generators import mock_get_feature_property
from tests.generators import ec2_max_age_days
from faker import Faker
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError
import pytest

older_than_max_age_date = datetime.now(timezone.utc) - timedelta(days=ec2_max_age_days + 1)
older_than_max_age_str = older_than_max_age_date.strftime("%m/%d/%Y, %H:%M:%S")
now_age_date = datetime.now(timezone.utc)
now_age_str = now_age_date.strftime("%m/%d/%Y, %H:%M:%S")
# used by test_delete_vpc_deleting_everything test. Needs to be global due to use in ec2_patch fixture
delete_vpc_calls_stack = []


# fixture setting up a commonly used mocks
@pytest.fixture
def ec2_patch(monkeypatch):
    def mocked_ec2_resource():
        pass

    def mocked_vpc(vpcId):
        return MockedVpc(vpcId)

    # used only in test_delete_vpc_deleting_everything. needs to be here because it is single place where we
    # mocking mocking ec2_resource
    def mocked_boto3_delete_vpc(VpcId):
        delete_vpc_calls_stack.append('boto3_delete_vpc')

    # only reason we need it is to mock long call chain
    def mocked_meta():
        pass

    # only reason we need it is to mock long call chain
    def mocked_client():
        pass

    monkeypatch.setattr(EC2, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    monkeypatch.setattr(EC2, 'get_all_regions', lambda self: ['region1'])
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(EC2, 'ec2_client', lambda self, region: MockedEC2Client())
    monkeypatch.setattr(EC2, 'ec2_resource', lambda self, region: mocked_ec2_resource)

    mocked_ec2_resource.Vpc = mocked_vpc
    mocked_ec2_resource.meta = mocked_meta
    mocked_ec2_resource.VpcPeeringConnection = lambda id: MockedVpcPeeringConnection()
    mocked_meta.client = mocked_client
    # don't mix up this with EC2.delete_vpc . this one is boto3 side of the call
    mocked_client.delete_vpc = mocked_boto3_delete_vpc
    return EC2('fake')


@pytest.fixture
def ec2_patch_for_vpc(ec2_patch, monkeypatch):
    def mocked_get_boolean(config_path, field=None):
        # all places where this fixture is called needs to have dry_run=False
        # most of tests except test_delete_vpc_exception_swallow does not care about vpc-notify-only
        # because delete_vpc ( only place where it currently used ) is mocked
        return config_path not in ['default/dry_run', 'cleanup/vpc-notify-only']

    # needs within emailnotify.send_mail
    def mocked_has(config_path):
        return config_path == 'notify'

    def mock_local_get_feature_property(feature: str, property: str, namespace: str = None):
        # within emailnotify.send_mail we needs sane strings
        if feature == 'notify' and property in ('to', 'from'):
            return 'email'
        else:
            return -1

    MockedEC2Client.response = {
        'Vpcs': [
            {'VpcId': 'someId', 'OwnerId': 'someId'}
        ]
    }
    monkeypatch.setattr(PCWConfig, 'getBoolean', mocked_get_boolean)
    monkeypatch.setattr(PCWConfig, 'has', mocked_has)
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_local_get_feature_property)
    monkeypatch.setattr('smtplib.SMTP', lambda arg1, arg2: MockedSMTP())
    return EC2('fake')


class MockedEC2Client():
    response = {}
    deleted_images = list()
    deleted_volumes = list()
    snapshotid_to_delete = 'delete_me'
    volumeid_to_delete = 'delete_me'
    snapshotid_i_have_ami = 'you_can_not_delete_me'
    delete_snapshot_raise_error = False
    delete_vpc_endpoints_called = False

    ec2_snapshots = {snapshotid_to_delete: 'snapshot', snapshotid_i_have_ami: 'snapshot'}

    def describe_images(self, *args, **kwargs):
        return MockedEC2Client.response

    def describe_snapshots(self, *args, **kwargs):
        return MockedEC2Client.response

    def deregister_image(self, *args, **kwargs):
        MockedEC2Client.deleted_images.append(kwargs['ImageId'])

    def delete_snapshot(self, SnapshotId):
        if MockedEC2Client.delete_snapshot_raise_error:
            error_response = {'Error': {'Code': 'InvalidSnapshot.InUse', 'Message': 'Message'}}
            raise ClientError(error_response=error_response, operation_name='delete_snapshot')
        else:
            MockedEC2Client.ec2_snapshots.pop(SnapshotId, None)

    def delete_volume(self, VolumeId):
        MockedEC2Client.deleted_volumes.append(VolumeId)

    def describe_volumes(self, *args, **kwargs):
        return MockedEC2Client.response

    def describe_vpcs(self, Filters):
        return MockedEC2Client.response

    def describe_vpc_endpoints(self, Filters):
        return MockedEC2Client.response

    def delete_vpc_endpoints(self, VpcEndpointIds):
        MockedEC2Client.delete_vpc_endpoints_called = True

    def describe_vpc_peering_connections(self, Filters):
        return MockedEC2Client.response


class MockedEKSClient():
    clusters_list = {}

    def list_clusters(self):
        return self.clusters_list

    def describe_cluster(self, name=None):
        if name == 'empty':
            return {}
        elif name == 'hascluster':
            return {'cluster': {}}
        elif name == 'hastags':
            return {'cluster': {'tags': {}}}
        elif name == 'ignored':
            return {'cluster': {'tags': {'pcw_ignore': '1'}}}
        else:
            return None


class MockedSMTP:
    mimetext = ''

    def ehlo(self):
        pass

    def sendmail(self, sender_email, receiver_email, mimetext):
        MockedSMTP.mimetext = mimetext


class MockedInstances:
    is_empty = False

    def all(self):
        if MockedInstances.is_empty:
            return []
        else:
            return ['subnet']


class MockedInterface:
    delete_called = False

    def delete(self):
        MockedInterface.delete_called = True


class MockedNetworkInterfaces:
    def all(self):
        return [MockedInterface()]


# this mock is used to replace several totally different classes
# but they all have common ground -> delete method
class MockedCollectionItem:
    delete_called = 0

    def __init__(self):
        # for mocking subnets while checking for running instances
        self.instances = MockedInstances()
        # for mocking subnets while deleting vpc_endpoints
        self.network_interfaces = MockedNetworkInterfaces()
        # for mocking internet gateways
        self.id = 'id'
        # for mocking routing tables
        self.associations_attribute = []
        # for mocking security_groups and also name should not be equal 'default'
        self.group_name = 'NOT_default'
        # for mocking network_acls should be False
        self.is_default = False

    def delete(self):
        MockedCollectionItem.delete_called += 1


class MockedCollectionWithAllMethod:

    def all(self):
        return [MockedCollectionItem()]


class MockedVpc:
    cnt_calls = 0
    detach_internet_gateway_called = 0

    def __init__(self, vpcId):
        MockedVpc.cnt_calls += 1
        self.subnets = MockedCollectionWithAllMethod()
        self.internet_gateways = MockedCollectionWithAllMethod()
        self.route_tables = MockedCollectionWithAllMethod()
        self.security_groups = MockedCollectionWithAllMethod()
        self.network_acls = MockedCollectionWithAllMethod()

    def detach_internet_gateway(self, InternetGatewayId):
        MockedVpc.detach_internet_gateway_called = 1


class MockedVpcPeeringConnection:
    delete_called = False

    def delete(self):
        MockedVpcPeeringConnection.delete_called = True


def test_cleanup_images_one_old(ec2_patch):
    MockedEC2Client.deleted_images = list()
    MockedEC2Client.response = {
        'Images': [
            {'Name': Faker().uuid4(), 'CreationDate': now_age_str, 'ImageId': 0},
            {'Name': Faker().uuid4(), 'CreationDate': older_than_max_age_str, 'ImageId': 2},
        ]
    }
    ec2_patch.cleanup_images(ec2_max_age_days)
    assert MockedEC2Client.deleted_images == [2]


def test_cleanup_images_all_new(ec2_patch):
    MockedEC2Client.deleted_images = list()
    MockedEC2Client.response = {
        'Images': [
            {'Name': Faker().uuid4(), 'CreationDate': now_age_str, 'ImageId': 0},
            {'Name': Faker().uuid4(), 'CreationDate': now_age_str, 'ImageId': 2},
        ]
    }
    ec2_patch.cleanup_images(ec2_max_age_days)
    assert MockedEC2Client.deleted_images == []


def test_is_outdated():
    assert EC2.is_outdated(older_than_max_age_date, ec2_max_age_days)
    assert not EC2.is_outdated(now_age_date, ec2_max_age_days)


def test_cleanup_snapshots_cleanup_all_new(ec2_patch):
    MockedEC2Client.response = {
        'Snapshots': [{'SnapshotId': MockedEC2Client.snapshotid_to_delete, 'StartTime': datetime.now()}]
    }
    ec2_patch.cleanup_snapshots(ec2_max_age_days)
    assert len(MockedEC2Client.ec2_snapshots) == 2


def test_cleanup_snapshots_cleanup_one_old(ec2_patch):
    MockedEC2Client.response = {
        'Snapshots': [{'SnapshotId': MockedEC2Client.snapshotid_to_delete, 'StartTime': older_than_max_age_date}]
    }
    ec2_patch.cleanup_snapshots(ec2_max_age_days)
    assert len(MockedEC2Client.ec2_snapshots) == 1


def test_cleanup_snapshots_have_ami(ec2_patch):
    MockedEC2Client.response = {
        'Snapshots': [{'SnapshotId': MockedEC2Client.snapshotid_i_have_ami, 'StartTime': datetime.now()}]
    }
    MockedEC2Client.delete_snapshot_raise_error = True
    ec2_patch.cleanup_snapshots(ec2_max_age_days)
    assert MockedEC2Client.snapshotid_i_have_ami in MockedEC2Client.ec2_snapshots


def test_cleanup_volumes_cleanupcheck(ec2_patch):
    MockedEC2Client.response = {
        'Volumes': [{'VolumeId': MockedEC2Client.volumeid_to_delete, 'CreateTime': older_than_max_age_date},
                    {'VolumeId': 'too_young_to_die', 'CreateTime': now_age_date},
                    {'VolumeId': MockedEC2Client.volumeid_to_delete, 'CreateTime': older_than_max_age_date,
                     'Tags': [{'Key': 'pcw_ignore', 'Value': '1'}]}, ]
    }
    ec2_patch.cleanup_volumes(ec2_max_age_days)
    assert len(MockedEC2Client.deleted_volumes) == 1
    assert MockedEC2Client.deleted_volumes[0] == MockedEC2Client.volumeid_to_delete


def test_cleanup_uploader_vpc_mail_sent_due_instances_associated(ec2_patch_for_vpc):
    MockedSMTP.mimetext = ''
    ec2_patch_for_vpc.cleanup_vpcs()
    assert 'Uploader leftover someId (OwnerId=someId) in region1 is locked' in MockedSMTP.mimetext


def test_cleanup_uploader_vpc_no_mail_sent_due_dry_run(ec2_patch_for_vpc):
    MockedSMTP.mimetext = ''
    ec2_patch_for_vpc.dry_run = True
    ec2_patch_for_vpc.cleanup_vpcs()
    assert MockedSMTP.mimetext == ''


def test_delete_vpc_deleting_everything(ec2_patch, monkeypatch):
    def mocked_delete_internet_gw(arg1, arg2):
        delete_vpc_calls_stack.append('delete_internet_gw')

    def mocked_delete_routing_tables(arg1, arg2):
        delete_vpc_calls_stack.append('delete_routing_tables')

    def mocked_delete_vpc_endpoints(arg1, arg2, arg3):
        delete_vpc_calls_stack.append('delete_vpc_endpoints')

    def mocked_delete_security_groups(arg1, arg2):
        delete_vpc_calls_stack.append('delete_security_groups')

    def mocked_delete_vpc_peering_connections(arg1, arg2, arg3):
        delete_vpc_calls_stack.append('delete_vpc_peering_connections')

    def mocked_delete_network_acls(arg1, arg2):
        delete_vpc_calls_stack.append('delete_network_acls')

    def mocked_delete_vpc_subnets(arg1, arg2):
        delete_vpc_calls_stack.append('delete_vpc_subnets')

        # emulated that there is no linked running instance to VPC which we trying to delete

    MockedInstances.is_empty = True
    monkeypatch.setattr(EC2, 'delete_internet_gw', mocked_delete_internet_gw)
    monkeypatch.setattr(EC2, 'delete_routing_tables', mocked_delete_routing_tables)
    monkeypatch.setattr(EC2, 'delete_vpc_endpoints', mocked_delete_vpc_endpoints)
    monkeypatch.setattr(EC2, 'delete_security_groups', mocked_delete_security_groups)
    monkeypatch.setattr(EC2, 'delete_vpc_peering_connections', mocked_delete_vpc_peering_connections)
    monkeypatch.setattr(EC2, 'delete_network_acls', mocked_delete_network_acls)
    monkeypatch.setattr(EC2, 'delete_vpc_subnets', mocked_delete_vpc_subnets)
    ec2_patch.delete_vpc('region', MockedVpc('vpcId'), 'vpcId')

    assert delete_vpc_calls_stack == ['delete_internet_gw', 'delete_routing_tables', 'delete_vpc_endpoints',
                                      'delete_security_groups', 'delete_vpc_peering_connections',
                                      'delete_network_acls',
                                      'delete_vpc_subnets', 'boto3_delete_vpc']


def test_delete_vpc_exception_swallow(ec2_patch_for_vpc, monkeypatch):
    def mocked_dont_call_it(arg1, arg2):
        raise Exception

    monkeypatch.setattr(EC2, 'delete_internet_gw', mocked_dont_call_it)
    ec2_patch_for_vpc.delete_vpc('region', MockedVpc('vpcId'), 'vpcId')
    assert 'Exception on VPC deletion' in MockedSMTP.mimetext
    assert 'self.delete_internet_gw(vpc)' in MockedSMTP.mimetext


def test_delete_vpc_no_delete_due_notify_only_config(ec2_patch_for_vpc, monkeypatch):
    def mocked_dont_call_it(arg1, arg2, arg3):
        raise Exception

    def mocked_get_boolean(config_path, field=None):
        return config_path != 'default/dry_run'

    monkeypatch.setattr(EC2, 'delete_vpc', mocked_dont_call_it)
    monkeypatch.setattr(PCWConfig, 'getBoolean', mocked_get_boolean)
    ec2_patch_for_vpc.cleanup_vpcs()
    assert 'VPC someId should be deleted, skipping due vpc-notify-only=True' in MockedSMTP.mimetext


def test_delete_internet_gw(ec2_patch):
    ec2_patch.delete_internet_gw(MockedVpc('vpcId'))
    assert MockedVpc.detach_internet_gateway_called == 1
    assert MockedCollectionItem.delete_called == 1


def test_delete_routing_tables(ec2_patch):
    ec2_patch.delete_routing_tables(MockedVpc('vpcId'))
    assert MockedCollectionItem.delete_called == 2


def test_delete_vpc_endpoints(ec2_patch):
    MockedEC2Client.response = {'VpcEndpoints': [{'VpcEndpointId': 'id'}]}
    ec2_patch.delete_vpc_endpoints('region', 'vpcId')
    assert MockedEC2Client.delete_vpc_endpoints_called


def test_delete_security_groups(ec2_patch):
    ec2_patch.delete_security_groups(MockedVpc('vpcId'))
    assert MockedCollectionItem.delete_called == 3


def test_delete_vpc_peering_connections(ec2_patch):
    MockedEC2Client.response = {'VpcPeeringConnections': [{'VpcPeeringConnectionId': 'id'}]}
    ec2_patch.delete_vpc_peering_connections('region', 'vpcId')
    assert MockedVpcPeeringConnection.delete_called


def test_delete_network_acls(ec2_patch):
    ec2_patch.delete_network_acls(MockedVpc('vpcId'))
    assert MockedCollectionItem.delete_called == 4


def test_delete_vpc_subnets(ec2_patch):
    ec2_patch.delete_vpc_subnets(MockedVpc('vpcId'))
    assert MockedCollectionItem.delete_called == 5
    assert MockedInterface.delete_called


def test_cleanup_all_calling_all(ec2_patch, monkeypatch):
    called_stack = []

    def mocked_cleanup_images(self, arg1):
        called_stack.append('cleanup_images')

    def mocked_cleanup_snapshots(self, arg1):
        called_stack.append('cleanup_snapshots')

    def mocked_cleanup_volumes(self, arg1):
        called_stack.append('cleanup_volumes')

    def mocked_cleanup_vpcs(self):
        called_stack.append('cleanup_vpcs')

    def mocked_get_boolean(config_path, field=None):
        return config_path != 'default/dry_run'

    monkeypatch.setattr(PCWConfig, 'getBoolean', mocked_get_boolean)
    monkeypatch.setattr(EC2, 'cleanup_images', mocked_cleanup_images)
    monkeypatch.setattr(EC2, 'cleanup_snapshots', mocked_cleanup_snapshots)
    monkeypatch.setattr(EC2, 'cleanup_volumes', mocked_cleanup_volumes)
    monkeypatch.setattr(EC2, 'cleanup_vpcs', mocked_cleanup_vpcs)
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda *args, **kwargs: 5)

    ec2_patch.cleanup_all()

    assert called_stack == ['cleanup_images', 'cleanup_snapshots', 'cleanup_volumes', 'cleanup_vpcs']


def test_list_clusters(ec2_patch, monkeypatch):
    mocked_eks = MockedEKSClient()
    monkeypatch.setattr(EC2, 'eks_client', lambda self, region: mocked_eks)
    all_clusters = ec2_patch.all_clusters()
    assert all_clusters == {}

    mocked_eks.clusters_list = {'clusters': ['empty']}
    all_clusters = ec2_patch.all_clusters()
    assert all_clusters == {}

    mocked_eks.clusters_list = {'clusters': ['hascluster']}
    all_clusters = ec2_patch.all_clusters()
    assert all_clusters == {}

    mocked_eks.clusters_list = {'clusters': ['hastags']}
    all_clusters = ec2_patch.all_clusters()
    assert all_clusters == {'region1': ['hastags']}

    mocked_eks.clusters_list = {'clusters': ['hastags', 'ignored']}
    all_clusters = ec2_patch.all_clusters()
    assert all_clusters == {'region1': ['hastags']}


class MockedKubernetesConfig():
    def load_kube_config(self, *args, **kwargs):
        return True


class MockedKubernetesClient():
    def __init__(self, jobs=[]):
        self.jobs = jobs
        self.deleted_jobs = []

    # pylint: disable=C0103
    def BatchV1Api(self):
        return self

    def list_job_for_all_namespaces(self, *args, **kwargs):
        return MockedKubernetesResult(self.jobs)

    def delete_namespaced_job(self, name, namespace):
        self.deleted_jobs.append(name)


class MockedKubernetesResult():
    def __init__(self, items):
        self.items = items


class MockedKubernetesJobStatus():
    def __init__(self, age):
        self.start_time = datetime.now(timezone.utc) - timedelta(days=age)


class MockedKubernetesJobMetadata():
    def __init__(self, name):
        self.name = name
        self.namespace = "default"


class MockedKubernetesJob():
    def __init__(self, name, age):
        self.status = MockedKubernetesJobStatus(age)
        self.metadata = MockedKubernetesJobMetadata(name)


class MockedSubprocessReturn():
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


@pytest.fixture
def k8s_patch(monkeypatch):
    monkeypatch.setattr(EC2, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    monkeypatch.setattr(EC2, 'get_all_regions', lambda self: ['region1'])
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)

    return EC2('fake')


def test_kubectl_client(k8s_patch, monkeypatch):
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(0))
    monkeypatch.setattr(kubernetes, 'config', MockedKubernetesConfig())
    mocked_client1 = MockedKubernetesClient(1)
    monkeypatch.setattr(kubernetes, 'client', mocked_client1)
    assert k8s_patch.kubectl_client("region1", "cluster") == mocked_client1

    # Check that the client is reused
    mocked_client2 = MockedKubernetesClient(1)
    monkeypatch.setattr(kubernetes, 'client', mocked_client2)
    assert k8s_patch.kubectl_client("region1", "cluster") == mocked_client1

    # Invalid 'aws eks update-kubeconfig' execution should return None
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(1))
    assert k8s_patch.kubectl_client("region2", "cluster") is None


def test_create_credentials_file(k8s_patch, monkeypatch):
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(0))
    k8s_patch.create_credentials_file("/tmp")
    assert os.path.exists("/tmp/.aws/credentials")

    # Invalid credentials, 'aws sts get-caller-identity' fails
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(1, "test"))
    error = None
    try:
        k8s_patch.create_credentials_file("/tmp")
    except Exception as exception:
        error = exception

    assert error is not None
    assert str(error) == "Invalid credentials, the credentials cannot be verified by'aws " + \
                         "sts get-caller-identity' with the error: test"


def test_cleanup_k8s_jobs(k8s_patch, monkeypatch):
    mocked_eks = MockedEKSClient()
    mocked_eks.clusters_list = {'clusters': ['cluster1']}
    monkeypatch.setattr(EC2, 'eks_client', lambda self, region: mocked_eks)

    monkeypatch.setattr(EC2, 'create_credentials_file', lambda *args, **kwargs: True)
    monkeypatch.setattr(kubernetes, 'config', MockedKubernetesConfig())
    mocked_kubernetes = MockedKubernetesClient([MockedKubernetesJob("job1", 1), MockedKubernetesJob("job2", 0)])
    monkeypatch.setattr(EC2, "kubectl_client", lambda *args, **kwargs: mocked_kubernetes)
    k8s_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 1
    assert mocked_kubernetes.deleted_jobs[0] == "job1"

    # test dry_run
    k8s_patch.dry_run = True
    mocked_kubernetes.deleted_jobs = []
    k8s_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 0
