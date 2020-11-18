from ocw.lib.EC2 import EC2
from webui.settings import PCWConfig
from tests.generators import mock_get_feature_property
from tests.generators import min_image_age_hours, max_image_age_hours
from datetime import datetime, timezone, timedelta
from botocore.exceptions import ClientError


def test_parse_image_name(monkeypatch):
    monkeypatch.setattr(EC2, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(EC2, 'get_all_regions', lambda self:['region1','region2'])
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda *args, **kwargs: "FOOF")
    ec2 = EC2('fake')

    assert ec2.parse_image_name('openqa-SLES12-SP5-EC2.x86_64-0.9.1-BYOS-Build1.55.raw.xz') == {
            'key': '12-SP5-EC2-BYOS-x86_64',
            'build': '0.9.1-1.55'
            }
    assert ec2.parse_image_name('openqa-SLES15-SP2.x86_64-0.9.3-EC2-HVM-Build1.10.raw.xz') == {
            'key': '15-SP2-EC2-HVM-x86_64',
            'build': '0.9.3-1.10'
            }
    assert ec2.parse_image_name('openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.10.raw.xz') == {
            'key': '15-SP2-EC2-HVM-BYOS-x86_64',
            'build': '0.9.3-1.10'
            }

    assert ec2.parse_image_name('openqa-SLES15-SP2.aarch64-0.9.3-EC2-HVM-Build1.49.raw.xz') == {
            'key': '15-SP2-EC2-HVM-aarch64',
            'build': '0.9.3-1.49'
            }

    assert ec2.parse_image_name('openqa-SLES12-SP4-EC2-HVM-BYOS.x86_64-0.9.2-Build2.56.raw.xz') == {
            'key': '12-SP4-EC2-HVM-BYOS-x86_64',
            'build': '0.9.2-2.56'
            }

    assert ec2.parse_image_name('openqa-SLES15-SP2-CHOST-BYOS.x86_64-0.9.3-EC2-Build1.11.raw.xz') == {
            'key': '15-SP2-EC2-CHOST-BYOS-x86_64',
            'build': '0.9.3-1.11'
            }

    assert ec2.parse_image_name('do not match') is None


def test_cleanup_images(monkeypatch):
    newer_then_min_age = datetime.now(timezone.utc).isoformat()
    older_then_min_age = (datetime.now(timezone.utc) - timedelta(hours=min_image_age_hours+1)).isoformat()
    older_then_max_age = (datetime.now(timezone.utc) - timedelta(hours=max_image_age_hours+1)).isoformat()

    response = {
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
    deleted_images = list()

    def mocked_ec2_client():
        pass
    mocked_ec2_client.describe_images = lambda *args, **kwargs: response
    mocked_ec2_client.deregister_image = lambda *args, **kwargs: deleted_images.append(kwargs['ImageId'])

    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(EC2, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(EC2, 'get_all_regions', lambda self:['region1'])
    monkeypatch.setattr(EC2, 'ec2_client', lambda self, region: mocked_ec2_client)

    ec2 = EC2('fake')
    ec2.cleanup_images()

    assert deleted_images == [2, 3, 4]

    deleted_images = list()
    response = {
        'Images': [
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.12.raw.xz',
             'CreationDate': older_then_min_age, 'ImageId': 3},
            {'Name': 'openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.13.raw.xz',
             'CreationDate': older_then_min_age, 'ImageId': 4},
        ]
    }
    ec2.cleanup_images()
    assert deleted_images == [3]


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

def test_cleanup_snapshots(monkeypatch):
    def mocked_ec2_client():
        pass

    snapshotid_to_delete = 'delete_me'
    snapshotid_i_have_ami = 'you_can_not_delete_me'

    ec2_snapshots = {snapshotid_to_delete: 'snapshot', snapshotid_i_have_ami: 'snapshot'}

    def delete_snapshot(SnapshotId):
        ec2_snapshots.pop(SnapshotId, None)


    response = {
        'Snapshots': [{'SnapshotId': snapshotid_to_delete,'StartTime': datetime.now()}]
        }
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda self, section, field: -1)
    monkeypatch.setattr(EC2, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(EC2, 'needs_to_delete_snapshot', lambda *args, **kwargs: True)
    monkeypatch.setattr(EC2, 'ec2_client', lambda self, region: mocked_ec2_client)
    monkeypatch.setattr(EC2, 'get_all_regions', lambda self: ['eu-central'])

    mocked_ec2_client.describe_snapshots = lambda OwnerIds: response
    mocked_ec2_client.delete_snapshot = delete_snapshot

    ec2 = EC2('fake')
    ec2.cleanup_snapshots()

    # deletion did not happened because cfgGet returned -1 ( setting not defined in pcw.ini )
    assert snapshotid_to_delete in ec2_snapshots

    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    ec2.cleanup_snapshots()

    # snapshot was deleted because setting **is** defined so whole cleanup start actually working
    assert snapshotid_to_delete not in ec2_snapshots

    def delete_snapshot_raise_error(SnapshotId):
        error_response = {'Error': {'Code': 'InvalidSnapshot.InUse','Message': 'Message'}}
        raise ClientError(error_response=error_response,operation_name='delete_snapshot')

    response = {
        'Snapshots': [{'SnapshotId': snapshotid_i_have_ami,'StartTime': datetime.now()}]
        }
    mocked_ec2_client.describe_snapshots = lambda OwnerIds: response
    mocked_ec2_client.delete_snapshot = delete_snapshot_raise_error

    ec2.cleanup_snapshots()
    assert snapshotid_i_have_ami in ec2_snapshots



