from ocw.lib.azure import Azure, Provider
from webui.PCWConfig import PCWConfig
from datetime import datetime, timezone, timedelta
from .generators import mock_get_feature_property
from tests import generators
from msrest.exceptions import AuthenticationError
from azure.core.exceptions import ResourceNotFoundError
from faker import Faker
import time
import pytest

deleted_images = list()


@pytest.fixture
def azure_patch(monkeypatch):
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    monkeypatch.setattr(Azure, 'check_credentials', lambda *args, **kwargs: True)
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    return Azure('fake')


@pytest.fixture
def container_client_all_new(monkeypatch):
    fakecontainerclient = FakeContainerClient([FakeBlob(), FakeBlob()])
    monkeypatch.setattr(Azure, 'container_client', lambda *args, **kwargs: fakecontainerclient)
    return fakecontainerclient


@pytest.fixture
def container_client_one_old(monkeypatch):
    old_times = datetime.now(timezone.utc) - timedelta(hours=generators.max_age_hours+1)
    fakecontainerclient = FakeContainerClient([FakeBlob(old_times, "to_be_deleted"), FakeBlob()])
    monkeypatch.setattr(Azure, 'container_client', lambda *args, **kwargs: fakecontainerclient)
    return fakecontainerclient


@pytest.fixture
def bs_client_no_pcw_ignore(monkeypatch):
    fakeblobserviceclient = FakeBlobServiceClient([FakeBlobContainer(), FakeBlobContainer()])
    monkeypatch.setattr(Azure, 'bs_client', lambda *args, **kwargs: fakeblobserviceclient)


@pytest.fixture
def bs_client_one_pcw_ignore(monkeypatch):
    fakeblobserviceclient = FakeBlobServiceClient([FakeBlobContainer({"pcw_ignore": "1"}), FakeBlobContainer()])
    monkeypatch.setattr(Azure, 'bs_client', lambda *args, **kwargs: fakeblobserviceclient)


class FakeResourceGroup:
    def __init__(self, name):
        self.name = name


class FakeGallery:
    def __init__(self, name):
        self.name = name


class FakeImage:
    def __init__(self, name):
        self.name = name


class FakeVersion:
    def __init__(self, name):
        self.name = name


@pytest.fixture
def mock_compute_mgmt_client(monkeypatch):
    global deleted_images
    deleted_images = list()

    def compute_mgmt_client(self):
        def client():
            pass
        client.images = lambda: None
        client.galleries = lambda: None
        client.gallery_images = lambda: None
        client.gallery_image_versions = lambda: None

        client.galleries.list_by_resource_group = lambda rg: [
            FakeGallery("gallery1"),
            FakeGallery("gallery2")
        ]

        client.gallery_images.list_by_gallery = lambda rg, gallery: {
            "gallery1": [FakeImage("image1")],
            "gallery2": [FakeImage("image2")]
        }[gallery]

        client.gallery_image_versions.list_by_gallery_image = lambda rg, gallery, image: {
            ("rg1", "gallery1", "image1"): [FakeVersion("v1"), FakeVersion("v2"), FakeVersion("v3")],
            ("rg1", "gallery2", "image2"): [FakeVersion("v1"), FakeVersion("v2")]
        }[(rg, gallery, image)]

        client.images.begin_delete = lambda rg, name: deleted_images.append(name)
        return client

    def resource_mgmt_client(self):
        def client():
            pass
        client.resource_groups = lambda: None
        client.resource_groups.list = lambda: [FakeResourceGroup("rg1")]
        return client

    monkeypatch.setattr(Azure, 'compute_mgmt_client', compute_mgmt_client)
    monkeypatch.setattr(Azure, 'resource_mgmt_client', resource_mgmt_client)


# This class is faking two unrelated entities:
# 1. Gallery returned by compute_mgmt_client.galleries.get
# 2. ImageDefinition returned by compute_mgmt_client.gallery_images.list_by_gallery
# But because all what we need in this case is "something what has property 'name'"
# it is fine to use same class
class FakeGalleryAndImageDefinition:

    def __init__(self) -> None:
        self.name = "name"


class FakeDisk:

    def __init__(self, managed_by=None):
        self.managed_by = managed_by


class FakeBlobContainer:

    def __init__(self, metadata=None, name=None):
        if metadata is None:
            metadata = []
        if name is None:
            self.name = "sle-images"
        else:
            self.name = name
        self.metadata = metadata

    def __getitem__(self, i):
        return self.metadata


class FakeBlob:

    def __init__(self, last_modified=None, name=None):
        if name is None:
            self.name = Faker().uuid4()
        else:
            self.name = name
        if last_modified is None:
            self.last_modified = datetime.now(timezone.utc)
        else:
            self.last_modified = last_modified


class FakeBlobServiceClient:

    def __init__(self, containers):
        self.containers = containers

    def list_containers(self, include_metadata):
        return self.containers


class FakeContainerClient:

    def list_blobs(self):
        return self.blobs

    def __init__(self, blobs):
        self.deleted_blobs = list()
        self.blobs = blobs

    def delete_blob(self, img_name, delete_snapshots):
        self.deleted_blobs.append(img_name)


class FakeItem:
    def __init__(self, changed_time=None, name=None):
        if changed_time is None:
            self.changed_time = datetime.now(timezone.utc)
        else:
            self.changed_time = changed_time
        if name is None:
            self.name = Faker().uuid4()
        else:
            self.name = name


def test_cleanup_blob_containers_all_new_no_pcw_ignore(azure_patch, container_client_all_new, bs_client_no_pcw_ignore):
    azure_patch.cleanup_blob_containers()
    assert container_client_all_new.deleted_blobs == []


def test_cleanup_blob_containers_one_old_no_pcw_ignore(azure_patch, container_client_one_old, bs_client_no_pcw_ignore):
    azure_patch.dry_run = True
    azure_patch.cleanup_blob_containers()
    assert container_client_one_old.deleted_blobs == []
    azure_patch.dry_run = False
    azure_patch.cleanup_blob_containers()
    assert container_client_one_old.deleted_blobs == ["to_be_deleted", "to_be_deleted"]


def test_cleanup_blob_containers_one_old_one_pcw_ignore(azure_patch, container_client_one_old, bs_client_one_pcw_ignore):
    azure_patch.dry_run = True
    azure_patch.cleanup_blob_containers()
    assert container_client_one_old.deleted_blobs == []
    azure_patch.dry_run = False
    azure_patch.cleanup_blob_containers()
    assert container_client_one_old.deleted_blobs == ["to_be_deleted"]


def test_cleanup_blob_containers_all_new_one_pcw_ignore(azure_patch, container_client_all_new, bs_client_one_pcw_ignore):
    azure_patch.cleanup_blob_containers()
    assert container_client_all_new.deleted_blobs == []


def test_cleanup_images_all_new(azure_patch, monkeypatch, mock_compute_mgmt_client):
    monkeypatch.setattr(Azure, 'list_resource', lambda *args, **kwargs: [FakeItem(), FakeItem()])
    azure_patch.cleanup_images()

    assert len(deleted_images) == 0


def test_cleanup_images_one_old(azure_patch, monkeypatch, mock_compute_mgmt_client):
    old_times = datetime.now(timezone.utc) - timedelta(hours=generators.max_age_hours+1)
    monkeypatch.setattr(Azure, 'list_resource', lambda *args, **kwargs: [FakeItem(old_times, "to_delete"), FakeItem()])
    azure_patch.dry_run = True
    azure_patch.cleanup_images()
    assert len(deleted_images) == 0

    azure_patch.dry_run = False
    azure_patch.cleanup_images()
    assert len(deleted_images) == 1
    assert deleted_images[0] == "to_delete"


def test_cleanup_disks_all_new(azure_patch, monkeypatch):

    global deleted_images
    # to make sure that we not failing due to other test left dirty env.
    deleted_images = list()

    def mock_compute_mgmt_client(self):
        def compute_mgmt_client():
            pass

        compute_mgmt_client.disks = lambda: None
        compute_mgmt_client.disks.begin_delete = lambda rg, name: deleted_images.append(name)
        compute_mgmt_client.disks.get = lambda rg, name: FakeDisk()
        return compute_mgmt_client

    monkeypatch.setattr(Azure, 'compute_mgmt_client', mock_compute_mgmt_client)

    monkeypatch.setattr(Azure, 'list_resource', lambda *args, **kwargs: [FakeItem(), FakeItem()])
    azure_patch.cleanup_disks()

    assert len(deleted_images) == 0


def test_cleanup_disks_one_old_no_managed_by(azure_patch, monkeypatch):
    global deleted_images
    # to make sure that we not failing due to other test left dirty env.
    deleted_images = list()

    def mock_compute_mgmt_client(self):
        def compute_mgmt_client():
            pass

        compute_mgmt_client.disks = lambda: None
        compute_mgmt_client.disks.begin_delete = lambda rg, name: deleted_images.append(name)
        compute_mgmt_client.disks.get = lambda rg, name: FakeDisk()
        return compute_mgmt_client

    monkeypatch.setattr(Azure, 'compute_mgmt_client', mock_compute_mgmt_client)

    old_times = datetime.now(timezone.utc) - timedelta(hours=generators.max_age_hours+1)
    monkeypatch.setattr(Azure, 'list_resource', lambda *args, **kwargs: [FakeItem(old_times, "to_delete"), FakeItem()])
    azure_patch.dry_run = True
    azure_patch.cleanup_disks()
    assert len(deleted_images) == 0

    azure_patch.dry_run = False
    azure_patch.cleanup_disks()
    assert len(deleted_images) == 1
    assert deleted_images[0] == "to_delete"


def test_cleanup_disks_one_old_with_managed_by(azure_patch, monkeypatch):
    global deleted_images
    # to make sure that we not failing due to other test left dirty env.
    deleted_images = list()

    def mock_compute_mgmt_client(self):
        def compute_mgmt_client():
            pass

        compute_mgmt_client.disks = lambda: None
        compute_mgmt_client.disks.begin_delete = lambda rg, name: deleted_images.append(name)
        compute_mgmt_client.disks.get = lambda rg, name: FakeDisk("I am busy")
        return compute_mgmt_client

    monkeypatch.setattr(Azure, 'compute_mgmt_client', mock_compute_mgmt_client)

    old_times = datetime.now(timezone.utc) - timedelta(hours=generators.max_age_hours+1)
    monkeypatch.setattr(Azure, 'list_resource', lambda *args, **kwargs: [FakeItem(old_times, "to_delete"), FakeItem()])
    azure_patch.cleanup_disks()

    assert len(deleted_images) == 0


def test_cleanup_all(azure_patch, monkeypatch):
    called = 0

    def count_call(*args, **kwargs):
        nonlocal called
        called = called + 1

    monkeypatch.setattr(Azure, 'get_storage_key', lambda *args, **kwargs: 'FOOXX')
    monkeypatch.setattr(Azure, 'cleanup_blob_containers', count_call)
    monkeypatch.setattr(Azure, 'cleanup_disks', count_call)
    monkeypatch.setattr(Azure, 'cleanup_images', count_call)
    monkeypatch.setattr(Azure, 'cleanup_gallery_img_versions', count_call)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')

    az = Azure('fake')
    az.cleanup_all()
    assert called == 4


def test_check_credentials(monkeypatch):
    count_list_resource_groups = 0
    failed_list_resource_groups = 0

    def mock_list_resource_groups(self):
        nonlocal count_list_resource_groups
        count_list_resource_groups = count_list_resource_groups + 1
        if count_list_resource_groups > failed_list_resource_groups:
            return True
        raise AuthenticationError("OHA Mocked auth error")

    monkeypatch.setattr(Azure, 'list_resource_groups', mock_list_resource_groups)
    monkeypatch.setattr(time, 'sleep', lambda *args, **kwargs: True)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **
                        kwargs: {'client_id': 'fake'})
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)

    count_list_resource_groups = 0
    failed_list_resource_groups = 3
    Azure('fake')
    assert count_list_resource_groups == 4

    count_list_resource_groups = 0
    failed_list_resource_groups = 5
    with pytest.raises(AuthenticationError):
        Azure('fake')


def test_container_valid_for_cleanup():
    assert Azure.container_valid_for_cleanup(FakeBlobContainer({}, "random name")) is False
    assert Azure.container_valid_for_cleanup(FakeBlobContainer({}, "sle-images")) is True
    assert Azure.container_valid_for_cleanup(FakeBlobContainer({}, "bootdiagnostics-dsfsdfsdf")) is True
    assert Azure.container_valid_for_cleanup(FakeBlobContainer({"pcw_ignore": "1"}, "bootdiagnostics-asdxyz")) is False
    assert Azure.container_valid_for_cleanup(FakeBlobContainer({"pcw_ignore": "1"}, "sle-images")) is False


def test_get_vm_types_in_resource_group(azure_patch, monkeypatch):
    azure = Azure('fake')

    vms_list = list()

    class MockedHWProfile:

        def __init__(self, vmtype):
            self.vm_size = vmtype

    class MockVM:

        def __init__(self, vmtype):
            self.hardware_profile = MockedHWProfile(vmtype)

    def mocked_list(name):
        if name == 'fire!!!':
            raise ResourceNotFoundError
        else:
            return vms_list

    def mock_compute_mgmt_client(self):
        def compute_mgmt_client():
            pass

        compute_mgmt_client.virtual_machines = lambda: None
        compute_mgmt_client.virtual_machines.list = mocked_list
        return compute_mgmt_client

    monkeypatch.setattr(Azure, 'compute_mgmt_client', mock_compute_mgmt_client)

    # when there is no VMs we returning 'N/A'
    ret = azure.get_vm_types_in_resource_group('fake')
    assert ret == 'N/A'

    vms_list.append(MockVM('fake'))

    # when single VM is in the list we returning name of type of this VM
    ret = azure.get_vm_types_in_resource_group('fake')
    assert ret == 'fake'

    vms_list.append(MockVM('fake'))

    # now there are two VMs with same type but we returning same string
    # because we don't want to duplicate same type again
    ret = azure.get_vm_types_in_resource_group('fake')
    assert ret == 'fake'

    vms_list.append(MockVM('anotherfake'))

    # now we have two VMs with same type and 3d with different one
    ret = azure.get_vm_types_in_resource_group('fake')
    assert 'anotherfake' in ret
    assert 'fake' in ret

    vms_list.append(MockVM('fake'))

    # when one of VMs throw azure.core.exceptions.ResourceNotFoundError we returning None
    ret = azure.get_vm_types_in_resource_group('fire!!!')
    assert ret is None


def test_get_img_versions_count(azure_patch, mock_compute_mgmt_client):
    assert Azure('fake').get_img_versions_count() == 5
