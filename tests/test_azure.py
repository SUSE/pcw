from ocw.lib.azure import Azure
from webui.settings import ConfigFile


def test_parse_image_name(monkeypatch):
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(ConfigFile, 'get', lambda *args, **kwargs: "FOOF")
    az = Azure('fake')

    assert az.parse_image_name('SLES12-SP5-Azure.x86_64-0.9.1-SAP-BYOS-Build3.3.vhd') == {
        'key': '12-SP5-SAP-BYOS-x86_64',
        'build': '0.9.1-3.3'
    }

    assert az.parse_image_name('SLES15-SP2-BYOS.x86_64-0.9.3-Azure-Build1.10.vhd') == {
        'key': '15-SP2-Azure-BYOS-x86_64',
        'build': '0.9.3-1.10'
    }
    assert az.parse_image_name('SLES15-SP2.x86_64-0.9.3-Azure-Basic-Build1.11.vhd') == {
        'key': '15-SP2-Azure-Basic-x86_64',
        'build': '0.9.3-1.11'
    }

    assert az.parse_image_name('SLES15-SP2-SAP-BYOS.x86_64-0.9.2-Azure-Build1.9.vhd') == {
        'key': '15-SP2-Azure-SAP-BYOS-x86_64',
        'build': '0.9.2-1.9'
    }
    assert az.parse_image_name('SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd') == {
        'key': '15-SP2-Azure-HPC-x86_64',
        'build': '0.9.0-1.43'
    }
    assert az.parse_image_name('SLES15-SP2-BYOS.aarch64-0.9.3-Azure-Build2.36.vhdfixed.x') == {
        'key': '15-SP2-Azure-BYOS-aarch64',
        'build': '0.9.3-2.36'
    }

    assert az.parse_image_name('do not match') is None
