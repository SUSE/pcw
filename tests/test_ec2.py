from ocw.lib.EC2 import EC2
from ocw.lib.provider import Provider
from webui.settings import ConfigFile
from tests.generators import mock_cfgGet
from tests.generators import min_image_age_hours, max_image_age_hours
from datetime import datetime, timezone, timedelta


def test_parse_image_name(monkeypatch):
    monkeypatch.setattr(EC2, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(ConfigFile, 'get', lambda *args, **kwargs: "FOOF")
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


def test_cleanup_all(monkeypatch):
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

    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    monkeypatch.setattr(EC2, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(EC2, 'ec2_client', lambda self: mocked_ec2_client)

    ec2 = EC2('fake')
    ec2.cleanup_all()

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
    ec2.cleanup_all()
    assert deleted_images == [3]


