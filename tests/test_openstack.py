from collections import namedtuple
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from pytest import fixture
from ocw.lib.openstack import Openstack
from webui.PCWConfig import PCWConfig


def assert_not_called_with(self, *args, **kwargs):
    try:
        self.assert_called_with(*args, **kwargs)
    except AssertionError:
        return
    raise AssertionError('Expected %s to not have been called.' % self._format_mock_call_signature(args, kwargs))


MagicMock.assert_not_called_with = assert_not_called_with


@fixture
def openstack_instance():
    with patch.object(Openstack, 'read_auth_json', return_value={}):
        with patch.object(Openstack, 'get_data', return_value="CustomRegion"):
            with patch('openstack.connect') as mock_connect:
                mock_client = MagicMock()
                mock_connect.return_value = mock_client
                yield Openstack('test_namespace')


def test_is_outdated(openstack_instance):
    now = datetime.now(timezone.utc)

    max_days = 10
    patch.object(PCWConfig, 'get_feature_property', return_value=max_days)

    # Test cases with different timestamps and max_days values
    test_cases = [
        # Timestamp is within the valid range
        {
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "expected": False,
        },
        # Timestamp is exactly at the max_days limit
        {
            "timestamp": (now - timedelta(days=max_days)).isoformat(),
            "expected": True,
        },
        # Timestamp exceeds the max_days limit
        {
            "timestamp": (now - timedelta(days=max_days+1)).isoformat(),
            "expected": True,
        },
        # Timestamp is in the future
        {
            "timestamp": (now + timedelta(days=max_days+1)).isoformat(),
            "expected": False,
        },
    ]

    for test in test_cases:
        assert openstack_instance.is_outdated(test["timestamp"], "openstack-vm-max-age-days") == test["expected"]


def test_cleanup_all(openstack_instance):
    openstack_instance.cleanup_all()
    openstack_instance.client().compute.servers.assert_called_once()
    openstack_instance.client().image.images.assert_called_once()
    openstack_instance.client().list_keypairs.assert_called_once()


def test_cleanup_instances(openstack_instance):
    # Prepare test data
    outdated_server = MagicMock()
    outdated_server.name = 'openqa-vm-outdated'
    outdated_server.created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()

    recent_server = MagicMock()
    recent_server.name = 'openqa-vm-recent'
    recent_server.created_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    openstack_instance.client().compute.servers.return_value = [outdated_server, recent_server]

    # Test with dry_run=False
    openstack_instance.dry_run = False
    openstack_instance._cleanup_instances()

    kwargs = {'wait': False, 'timeout': 180, 'delete_ips': True, 'delete_ip_retry': 1}
    openstack_instance.client().delete_server.assert_called_once_with(outdated_server.name, **kwargs)
    openstack_instance.client().delete_server.assert_not_called_with(recent_server.name)

    # Reset mocks
    openstack_instance.client().delete_server.reset_mock()

    # Test with dry_run=True
    openstack_instance.dry_run = True
    openstack_instance._cleanup_instances()

    openstack_instance.client().delete_server.assert_not_called()


def test_cleanup_images(openstack_instance):
    Image = namedtuple('Image', ['name', 'created_at', 'tags'])

    # Prepare test data
    max_days = 7
    patch.object(PCWConfig, 'get_feature_property', return_value=max_days)
    images = [
        Image(
            name='openqa-image-outdated',
            created_at=(datetime.now(timezone.utc) - timedelta(days=max_days+1)).isoformat(),
            tags=['openqa'],
        ),
        Image(
            name='openqa-image-recent',
            created_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            tags=['openqa'],
        ),
        Image(
            name='not-openqa-image',
            created_at=(datetime.now(timezone.utc) - timedelta(days=max_days+1)).isoformat(),
            tags=[],
        ),
    ]
    openstack_instance.client().image.images.return_value = images

    # Test with dry_run=False
    openstack_instance.dry_run = False
    openstack_instance._cleanup_images()

    kwargs = {'wait': False, 'timeout': 3600}
    openstack_instance.client().delete_image.assert_called_once_with(images[0].name, **kwargs)
    openstack_instance.client().delete_image.assert_not_called_with(images[1].name)
    openstack_instance.client().delete_image.assert_not_called_with(images[2].name)

    # Reset mocks
    openstack_instance.client().delete_image.reset_mock()

    # Test with dry_run=True
    openstack_instance.dry_run = True
    openstack_instance._cleanup_images()

    openstack_instance.client().delete_image.assert_not_called()


def test_cleanup_keypairs(openstack_instance):
    Keypair = namedtuple('Keypair', ['name', 'created_at'])

    # Prepare test data
    max_days = 3
    keypairs = [
        Keypair(
            name='openqa-keypair-outdated',
            created_at=(datetime.now(timezone.utc) - timedelta(days=max_days+1)).isoformat(),
        ),
        Keypair(
            name='openqa-keypair-recent',
            created_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
        ),
        Keypair(
            name='not-openqa-keypair',
            created_at=(datetime.now(timezone.utc) - timedelta(days=max_days+1)).isoformat(),
        ),
    ]
    openstack_instance.client().list_keypairs.return_value = keypairs

    # Test with dry_run=False
    openstack_instance.dry_run = False
    openstack_instance._cleanup_keypairs()

    openstack_instance.client().delete_keypair.assert_called_once_with(keypairs[0].name)
    openstack_instance.client().delete_keypair.assert_not_called_with(keypairs[1].name)
    openstack_instance.client().delete_keypair.assert_not_called_with(keypairs[2].name)

    # Reset mocks
    openstack_instance.client().delete_keypair.reset_mock()

    # Test with dry_run=True
    openstack_instance.dry_run = True
    openstack_instance._cleanup_keypairs()

    openstack_instance.client().delete_keypair.assert_not_called()
