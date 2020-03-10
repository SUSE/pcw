from ocw.lib.azure import Azure
from ocw.lib.provider import Provider
from webui.settings import ConfigFile
from azure.storage.blob import BlockBlobService
from .generators import MockImage
from .generators import generate_mocked_images_older_than
from .generators import mock_cfgGet


delete_calls = {'quantity': [], 'old': [], 'young': []}


def delete_blob_mock(self, container_name, img_name, snapshot=None):
    delete_calls[container_name].append(img_name)


def list_blobs_mock(self, container_name):
    if container_name == 'quantity':
        return generate_mocked_images_older_than(8)
    elif container_name == 'old':
        return generate_mocked_images_older_than(25)
    else:
        return generate_mocked_images_older_than(1)


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


def test_cleanup_sle_images_container_too_many(monkeypatch):
    test_name = 'quantity'
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(BlockBlobService, 'list_blobs', list_blobs_mock)
    monkeypatch.setattr(BlockBlobService, 'delete_blob', delete_blob_mock)
    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    az = Azure('fake')
    az.cleanup_sle_images_container(BlockBlobService(account_name='openqa', account_key='www'), test_name)
    deleted = ['SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd', 'SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd',
               'SLES15-SP2-BYOS.x86_64-0.9.3-Azure-Build2.36.vhd', 'SLES15-SP2-BYOS.x86_64-0.9.6-Azure-Build1.3.vhd']
    for item in deleted:
        assert item in delete_calls[test_name]


def test_cleanup_sle_images_container_too_young(monkeypatch):
    test_name = 'young'
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(BlockBlobService, 'list_blobs', list_blobs_mock)
    monkeypatch.setattr(BlockBlobService, 'delete_blob', delete_blob_mock)
    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    az = Azure('fake')
    az.cleanup_sle_images_container(BlockBlobService(account_name='openqa', account_key='www'), test_name)
    assert len(delete_calls[test_name]) == 0


def test_cleanup_sle_images_container_too_old(monkeypatch):
    test_name = 'old'
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(BlockBlobService, 'list_blobs', list_blobs_mock)
    monkeypatch.setattr(BlockBlobService, 'delete_blob', delete_blob_mock)
    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    az = Azure('fake')
    az.cleanup_sle_images_container(BlockBlobService(account_name='openqa', account_key='www'), test_name)
    assert len(delete_calls[test_name]) == 6
