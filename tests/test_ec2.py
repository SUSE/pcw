from ocw.lib.EC2 import EC2
from webui.settings import PCWConfig
from tests.generators import mock_get_feature_property
from tests.generators import min_image_age_hours, max_image_age_hours, ec2_max_volumes_age_days, \
    ec2_max_snapshot_age_days
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError
import pytest

older_then_min_age = (datetime.now(timezone.utc) - timedelta(hours=min_image_age_hours + 1)).isoformat()
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
    monkeypatch.setattr(EC2, 'get_all_regions', lambda self: ['region1'])
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(EC2, 'ec2_client', lambda self, region: MockedEC2Client())
    monkeypatch.setattr(EC2, 'needs_to_delete_snapshot', lambda *args, **kwargs: True)
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
    deleted_sg = list()
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

    def delete_security_group(self, GroupId):
        MockedEC2Client.deleted_sg.append(GroupId)

    def describe_security_groups(self):
        return MockedEC2Client.response


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


def test_parse_image_name(ec2_patch):
    assert ec2_patch.parse_image_name('openqa-SLES12-SP5-EC2.x86_64-0.9.1-BYOS-Build1.55.raw.xz') == {
        'key': '12-SP5-EC2-BYOS-x86_64',
        'build': '0.9.1-1.55'
    }
    assert ec2_patch.parse_image_name('openqa-SLES15-SP2.x86_64-0.9.3-EC2-HVM-Build1.10.raw.xz') == {
        'key': '15-SP2-EC2-HVM-x86_64',
        'build': '0.9.3-1.10'
    }
    assert ec2_patch.parse_image_name('openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.10.raw.xz') == {
        'key': '15-SP2-EC2-HVM-BYOS-x86_64',
        'build': '0.9.3-1.10'
    }
    assert ec2_patch.parse_image_name('openqa-SLES15-SP2.aarch64-0.9.3-EC2-HVM-Build1.49.raw.xz') == {
        'key': '15-SP2-EC2-HVM-aarch64',
        'build': '0.9.3-1.49'
    }
    assert ec2_patch.parse_image_name('openqa-SLES12-SP4-EC2-HVM-BYOS.x86_64-0.9.2-Build2.56.raw.xz') == {
        'key': '12-SP4-EC2-HVM-BYOS-x86_64',
        'build': '0.9.2-2.56'
    }
    assert ec2_patch.parse_image_name('openqa-SLES15-SP2-CHOST-BYOS.x86_64-0.9.3-EC2-Build1.11.raw.xz') == {
        'key': '15-SP2-EC2-CHOST-BYOS-x86_64',
        'build': '0.9.3-1.11'
    }
    assert ec2_patch.parse_image_name('do not match') is None


def test_cleanup_images_delete_due_time(ec2_patch):
    newer_then_min_age = datetime.now(timezone.utc).isoformat()
    older_then_max_age = (datetime.now(timezone.utc) - timedelta(hours=max_image_age_hours + 1)).isoformat()
    MockedEC2Client.deleted_images = list()
    MockedEC2Client.response = {
        'Images': [
            {'Name': 'SomeThingElse',
             'CreationDate': older_then_max_age, 'ImageId': 0},
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.10.raw.xz',
             'CreationDate': newer_then_min_age, 'ImageId': 1},
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.11.raw.xz',
             'CreationDate': older_then_min_age, 'ImageId': 2},
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.12.raw.xz',
             'CreationDate': older_then_min_age, 'ImageId': 3},
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.13.raw.xz',
             'CreationDate': older_then_max_age, 'ImageId': 4},
        ]
    }
    ec2_patch.cleanup_images()
    assert MockedEC2Client.deleted_images == [2, 3, 4]


def test_cleanup_images_delete_due_quantity(ec2_patch):
    MockedEC2Client.deleted_images = list()
    MockedEC2Client.response = {
        'Images': [
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.12.raw.xz',
             'CreationDate': older_then_min_age, 'ImageId': 3},
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.13.raw.xz',
             'CreationDate': older_then_min_age, 'ImageId': 4},
        ]
    }
    ec2_patch.cleanup_images()
    assert MockedEC2Client.deleted_images == [3]


def test_needs_to_delete_snapshot():
    days_to_delete = 1
    old_enough = datetime.now() - timedelta(days=days_to_delete + 1)
    correct_description1 = 'OpenQA upload image'
    correct_description2 = 'Created by CreateImage(jsdkfhsdkj) for ami-sdjhfksdj from vol-sdjfhksdjh'
    snapshot_to_delete = {'StartTime': old_enough, 'Description': correct_description1}
    snapshot_to_delete2 = {'StartTime': old_enough, 'Description': correct_description2}
    not_old_enough = {'StartTime': datetime.now(), 'Description': correct_description1}
    wrong_description = {'StartTime': old_enough, 'Description': 'DDDDDDDDD'}
    assert EC2.needs_to_delete_snapshot(snapshot_to_delete, days_to_delete)
    assert EC2.needs_to_delete_snapshot(snapshot_to_delete2, days_to_delete)
    assert not EC2.needs_to_delete_snapshot(not_old_enough, days_to_delete)
    assert not EC2.needs_to_delete_snapshot(wrong_description, days_to_delete)


def test_cleanup_snapshots_cleanup_check(ec2_patch):
    MockedEC2Client.response = {
        'Snapshots': [{'SnapshotId': MockedEC2Client.snapshotid_to_delete, 'StartTime': datetime.now()}]
    }
    ec2_patch.cleanup_snapshots(ec2_max_snapshot_age_days)
    # snapshot was deleted because setting **is** defined so whole cleanup start actually working
    assert MockedEC2Client.snapshotid_to_delete not in MockedEC2Client.ec2_snapshots


def test_cleanup_snapshots_have_ami(ec2_patch):
    MockedEC2Client.response = {
        'Snapshots': [{'SnapshotId': MockedEC2Client.snapshotid_i_have_ami, 'StartTime': datetime.now()}]
    }
    MockedEC2Client.delete_snapshot_raise_error = True
    ec2_patch.cleanup_snapshots(ec2_max_snapshot_age_days)
    assert MockedEC2Client.snapshotid_i_have_ami in MockedEC2Client.ec2_snapshots


def test_cleanup_volumes_cleanupcheck(ec2_patch):
    MockedEC2Client.response = {
        'Volumes': [{'VolumeId': MockedEC2Client.volumeid_to_delete,
                     'CreateTime': datetime.now(timezone.utc) - timedelta(days=ec2_max_volumes_age_days + 1)},
                    {'VolumeId': 'too_young_to_die', 'CreateTime': datetime.now(timezone.utc) - timedelta(days=2)},
                    {'VolumeId': MockedEC2Client.volumeid_to_delete,
                     'CreateTime': datetime.now(timezone.utc) - timedelta(days=ec2_max_volumes_age_days + 1),
                     'Tags': [{'Key': 'DO_NOT_DELETE', 'Value': '1'}]}, ]
    }
    ec2_patch.cleanup_volumes(ec2_max_volumes_age_days)
    assert len(MockedEC2Client.deleted_volumes) == 1
    assert MockedEC2Client.deleted_volumes[0] == MockedEC2Client.volumeid_to_delete


def test_cleanup_uploader_vpc_mail_sent_due_instances_associated(ec2_patch_for_vpc):
    MockedSMTP.mimetext = ''
    ec2_patch_for_vpc.cleanup_uploader_vpcs()
    assert 'Uploader leftover someId (OwnerId=someId) in region1 is locked' in MockedSMTP.mimetext


def test_cleanup_uploader_vpc_no_mail_sent_due_dry_run(ec2_patch_for_vpc):
    MockedSMTP.mimetext = ''
    ec2_patch_for_vpc.dry_run = True
    ec2_patch_for_vpc.cleanup_uploader_vpcs()
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
    ec2_patch_for_vpc.cleanup_uploader_vpcs()
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

    def mocked_cleanup_images(self):
        called_stack.append('cleanup_images')

    def mocked_cleanup_sg(self):
        called_stack.append('cleanup_sg')

    def mocked_cleanup_snapshots(self, arg1):
        called_stack.append('cleanup_snapshots')

    def mocked_cleanup_volumes(self, arg1):
        called_stack.append('cleanup_volumes')

    def mocked_cleanup_uploader_vpcs(self):
        called_stack.append('cleanup_uploader_vpcs')

    def mocked_get_boolean(config_path, field=None):
        return config_path != 'default/dry_run'

    monkeypatch.setattr(PCWConfig, 'getBoolean', mocked_get_boolean)
    monkeypatch.setattr(EC2, 'cleanup_images', mocked_cleanup_images)
    monkeypatch.setattr(EC2, 'cleanup_snapshots', mocked_cleanup_snapshots)
    monkeypatch.setattr(EC2, 'cleanup_volumes', mocked_cleanup_volumes)
    monkeypatch.setattr(EC2, 'cleanup_uploader_vpcs', mocked_cleanup_uploader_vpcs)
    monkeypatch.setattr(EC2, 'cleanup_sg', mocked_cleanup_sg)
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda *args, **kwargs: 5)

    ec2_patch.cleanup_all()

    assert called_stack == ['cleanup_images', 'cleanup_snapshots',
                            'cleanup_volumes', 'cleanup_uploader_vpcs', 'cleanup_sg']


def test_cleanup_sg_cleanup_one_group(ec2_patch):
    openqa_ttl = 75000
    ttl_not_expired = datetime.now(timezone.utc).isoformat()
    ttl_expired = (datetime.now(timezone.utc) - timedelta(seconds=openqa_ttl + 10)).isoformat()
    MockedEC2Client.response = {
        'SecurityGroups': [
            {'Tags': [{'Key': 'openqa_created_date', 'Value': ttl_expired},
                      {'Key': 'openqa_ttl', 'Value': openqa_ttl}], 'GroupName': 'TTL_Expired', 'GroupId': '11'},
            {'Tags': [{'Key': 'openqa_created_date', 'Value': ttl_not_expired},
                      {'Key': 'openqa_ttl', 'Value': openqa_ttl}], 'GroupName': 'TTL_NOT_Expired', 'GroupId': '12'},
            {'Tags': [{'Key': 'openqa_created_date', 'Value': ttl_expired},
                      {'Key': 'openqa_ttl', 'Value': openqa_ttl}], 'GroupName': 'TTL_Expired2', 'GroupId': '13'},
        ]
    }
    ec2_patch.cleanup_sg()
    assert len(MockedEC2Client.deleted_sg) == 2
    assert '11' in MockedEC2Client.deleted_sg

