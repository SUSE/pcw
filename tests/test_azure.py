from ocw.lib.azure import Azure
from ocw.lib.provider import Provider
from webui.settings import ConfigFile
from azure.storage.blob import BlockBlobService
from datetime import datetime, timezone, timedelta
from .generators import MockImage
from .generators import generate_mocked_images_older_than
from .generators import mock_cfgGet
from tests import generators


delete_calls = {'quantity': [], 'old': [], 'young': []}


def delete_blob_mock(self, container_name, img_name, snapshot=None):
    delete_calls[container_name].append(img_name)


def list_blobs_mock(self, container_name):
    last_modified = datetime.now()
    return [MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd'),
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd'),
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.7.vhd'),
            MockImage('SLES15-SP2-BYOS.x86_64-0.9.3-Azure-Build2.36.vhd', last_modified),
            MockImage('SLES15-SP2-BYOS.x86_64-0.9.6-Azure-Build1.3.vhd', last_modified),
            MockImage('SLES15-SP2-BYOS.x86_64-0.9.6-Azure-Build1.9.vhd', last_modified)
            ]


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


def test_cleanup_sle_images_container(monkeypatch):
    class FakeBlockBlobService:
        deleted_blobs = list()

        def list_blobs(self, container):
            return [
                    MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd'),
                    MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd'),
                    MockImage('YouWillNotGetMyBuildNumber'),
                ]

        def delete_blob(self, container_name, img_name,  snapshot):
            self.deleted_blobs.append(img_name)

    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    az = Azure('fake')
    bbsrv = FakeBlockBlobService()
    keep_images = ['SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd']

    az.cleanup_sle_images_container(bbsrv, keep_images)
    assert bbsrv.deleted_blobs == ['SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd']


def test_cleanup_images_from_rg(monkeypatch):
    deleted_images = list()
    items = [
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd'),
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd'),
            MockImage('YouWillNotGetMyBuildNumber'),
            ]

    def mock_res_mgmt_client(self):
        def res_mgmt_client():
            pass
        res_mgmt_client.resources = lambda: None
        res_mgmt_client.resources.list_by_resource_group = lambda *args, **kwargs: items
        return res_mgmt_client

    def mock_compute_mgmt_client(self):
        def compute_mgmt_client():
            pass
        compute_mgmt_client.images = lambda: None
        compute_mgmt_client.images.delete = lambda rg, name: deleted_images.append(name)
        return compute_mgmt_client

    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(Azure, 'resource_mgmt_client', mock_res_mgmt_client)
    monkeypatch.setattr(Azure, 'compute_mgmt_client', mock_compute_mgmt_client)

    az = Azure('fake')
    keep_images = ['SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd']
    az.cleanup_images_from_rg(keep_images)
    assert deleted_images == ['SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd']


def test_cleanup_disks_from_rg(monkeypatch):
    deleted_disks = list()

    items = [
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd'),
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd'),
            MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.7.vhd'),
            MockImage('YouWillNotGetMyBuildNumber'),
            ]

    def mock_res_mgmt_client(self):
        def res_mgmt_client():
            pass
        res_mgmt_client.resources = lambda: None
        res_mgmt_client.resources.list_by_resource_group = lambda *args, **kwargs: items
        return res_mgmt_client

    def mock_compute_mgmt_client(self):
        class FakeDisk:
            def __init__(self, rg, name):
                self.managed_by = name == 'SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd'

        def compute_mgmt_client():
            pass
        compute_mgmt_client.disks = lambda: None
        compute_mgmt_client.disks.get = lambda rg, name: FakeDisk(rg, name)
        compute_mgmt_client.disks.delete = lambda rg, name: deleted_disks.append(name)
        return compute_mgmt_client

    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(Azure, 'resource_mgmt_client', mock_res_mgmt_client)
    monkeypatch.setattr(Azure, 'compute_mgmt_client', mock_compute_mgmt_client)

    keep_images = ['SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd']
    az = Azure('fake')
    az.cleanup_disks_from_rg(keep_images)
    assert deleted_disks == ['SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.7.vhd']


def test_get_keeping_image_names(monkeypatch):
    class FakeBlockBlobService:
        def list_blobs(self, container):
            older_then_min_age = datetime.now(timezone.utc) - timedelta(hours=generators.min_image_age_hours+1)
            return [
                    MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.0-Build1.43.vhd', older_then_min_age),
                    MockImage('SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd', older_then_min_age),
                    MockImage('YouWillNotGetMyBuildNumber', older_then_min_age),
                    ]

    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)

    az = Azure('fake')
    generators.max_images_per_flavor = 1
    assert az.get_keeping_image_names(FakeBlockBlobService()) == ['SLES15-SP2-Azure-HPC.x86_64-0.9.1-Build1.3.vhd']


def test_cleanup_all(monkeypatch):
    called = 0

    def count_call(*args, **kwargs):
        nonlocal called
        called = called + 1

    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: None)
    monkeypatch.setattr(Azure, 'get_storage_key', lambda *args, **kwargs: 'FOOXX')
    monkeypatch.setattr(Azure, 'get_keeping_image_names', lambda *args, **kwargs: ['a', 'b'])
    monkeypatch.setattr(Azure, 'cleanup_sle_images_container', count_call)
    monkeypatch.setattr(Azure, 'cleanup_disks_from_rg', count_call)
    monkeypatch.setattr(Azure, 'cleanup_images_from_rg', count_call)
    monkeypatch.setattr(Azure, 'cleanup_bootdiagnostics', count_call)

    az = Azure('fake')
    az.cleanup_all()
    assert called == 4


def test_cleanup_bootdiagnostics(monkeypatch):
    class FakeBlockBlobService:
        deleted_container = list()

        def list_containers(self):
            older_then_min_age = datetime.now(timezone.utc) - timedelta(hours=generators.min_image_age_hours+1)
            newer_then_min_age = datetime.now(timezone.utc)
            return [
                    MockImage('bootdiagnostics-A', older_then_min_age),
                    MockImage('bootdiagnostics-B', older_then_min_age),
                    MockImage('bootdiagnostics-C', newer_then_min_age),
                    MockImage('bootdiagnostics-D', newer_then_min_age),
                    MockImage('bootdiagnostics-E', older_then_min_age),
                ]

        def list_blobs(self, container):
            older_then_min_age = datetime.now(timezone.utc) - timedelta(hours=generators.min_image_age_hours+1)
            newer_then_min_age = datetime.now(timezone.utc)
            last_modified = older_then_min_age

            if (container == 'bootdiagnostics-E'):
                last_modified = newer_then_min_age

            return [MockImage('blalbub', last_modified)]

        def delete_container(self, container_name):
            self.deleted_container.append(container_name)

    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    bbs = FakeBlockBlobService()

    az = Azure('fake')
    az.cleanup_bootdiagnostics(bbs)

    assert bbs.deleted_container == [
            'bootdiagnostics-A',
            'bootdiagnostics-B',
            ]
