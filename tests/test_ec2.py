from ocw.lib.EC2 import EC2
from webui.settings import ConfigFile


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

    assert ec2.parse_image_name('do not match') is None
