from ocw.lib.provider import Provider, Image
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from tests import generators
from webui.settings import PCWConfig
from .generators import mock_get_feature_property
from .generators import max_images_per_flavor
from .generators import min_image_age_hours
from .generators import max_image_age_hours
import pytest


@pytest.fixture
def provider_patch(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda *args, **kwargs: 24)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')


def test_older_than_min_age_older(provider_patch):
    provider = Provider('testolderminage')
    assert provider.older_than_min_age(datetime.now(timezone.utc) - timedelta(hours=25)) == True


def test_older_than_min_age_younger(provider_patch):
    provider = Provider('testolderminage')
    assert provider.older_than_min_age(datetime.now(timezone.utc) - timedelta(hours=23)) == False


def test_needs_to_delete_image(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    provider = Provider('testneedstodelete')
    too_many_images = max_images_per_flavor+1
    not_enough_images = max_images_per_flavor-3
    older_than_min_age = datetime.now(timezone.utc) - timedelta(hours=min_image_age_hours+1)
    assert provider.needs_to_delete_image(too_many_images, datetime.now(timezone.utc)) == False
    assert provider.needs_to_delete_image(too_many_images, older_than_min_age) == True
    assert provider.needs_to_delete_image(not_enough_images, older_than_min_age) == False


def test_get_keeping_image_names(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    provider = Provider('testneedstodelete')

    newer_then_min_age = datetime.now(timezone.utc)
    older_then_min_age = datetime.now(timezone.utc) - timedelta(hours=min_image_age_hours+1)
    older_then_max_age = datetime.now(timezone.utc) - timedelta(hours=max_image_age_hours+1)

    generators.max_images_per_flavor = 1
    images = [
        Image('foo-A-0.0.1-0.1', 'A', '0.0.1-0.1', older_then_min_age),
        Image('foo-A-0.0.1-0.2', 'A', '0.0.1-0.2', older_then_min_age),
    ]
    assert provider.get_keeping_image_names(images) == ['foo-A-0.0.1-0.2']

    images = [
        Image('foo-A-0.0.1-0.1', 'A', '0.0.1-0.1', older_then_min_age),
        Image('foo-A-0.0.1-0.2', 'A', '0.0.1-0.2', older_then_max_age),
    ]
    assert provider.get_keeping_image_names(images) == []

    images = [
        Image('foo-A-0.0.1-0.1', 'A', '0.0.1-0.1', newer_then_min_age),
        Image('foo-A-0.0.1-0.2', 'A', '0.0.1-0.2', older_then_min_age),
    ]
    assert provider.get_keeping_image_names(images) == ['foo-A-0.0.1-0.2', 'foo-A-0.0.1-0.1']

    images = [
        Image('foo-A-0.0.1-0.1', 'A', '0.0.1-0.1', older_then_min_age),
        Image('foo-A-0.0.1-0.2', 'A', '0.0.1-0.2', older_then_min_age),
        Image('foo-B-0.0.1-0.1', 'B', '0.0.1-0.1', older_then_min_age),
        Image('foo-B-0.1.1-0.1', 'B', '0.1.1-0.1', older_then_min_age)
    ]
    assert provider.get_keeping_image_names(images) == ['foo-A-0.0.1-0.2', 'foo-B-0.1.1-0.1']

    generators.max_images_per_flavor = 2
    images = [
        Image('foo-A-0.0.1-0.1', 'A', '0.0.1-0.1', older_then_min_age),
        Image('foo-A-0.0.1-0.2', 'A', '0.0.1-0.2', older_then_min_age),
    ]
    assert provider.get_keeping_image_names(images) == ['foo-A-0.0.1-0.2', 'foo-A-0.0.1-0.1']


def test_getData(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: {"param1": "value1"})
    provider = Provider('testneedstodelete')

    assert provider.getData() == {'param1': 'value1'}
    assert provider.getData('param1') == 'value1'
