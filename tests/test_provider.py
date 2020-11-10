from ocw.lib.provider import Provider, Image
from .conftest import set_pcw_ini
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from tests import generators
from .generators import mock_cfgGet
from .generators import max_images_per_flavor
from .generators import min_image_age_hours
from .generators import max_image_age_hours


def test_cfgGet_with_defaults(pcw_file):
    provider = Provider('testns')
    assert provider.cfgGet('cleanup', 'max-images-per-flavor') == 1
    assert type(provider.cfgGet('cleanup', 'max-images-per-flavor')) is int
    assert type(provider.cfgGet('cleanup', 'min-image-age-hours')) is int
    assert type(provider.cfgGet('cleanup', 'max-image-age-hours')) is int
    assert provider.cfgGet('cleanup', 'azure-storage-resourcegroup') == 'openqa-upload'
    assert type(provider.cfgGet('cleanup', 'azure-storage-resourcegroup')) is str


def test_cfgGet_from_pcw_ini(pcw_file):
    set_pcw_ini(pcw_file, """
[cleanup]
max-images-per-flavor = 666
azure-storage-resourcegroup = bla-blub
""")
    provider = Provider('testns')
    assert provider.cfgGet('cleanup', 'max-images-per-flavor') == 666
    assert type(provider.cfgGet('cleanup', 'max-images-per-flavor')) is int
    assert provider.cfgGet('cleanup', 'azure-storage-resourcegroup') == 'bla-blub'
    assert type(provider.cfgGet('cleanup', 'azure-storage-resourcegroup')) is str


def test_cfgGet_from_pcw_ini_with_namespace(pcw_file):
    set_pcw_ini(pcw_file, """
[cleanup]
max-images-per-flavor = 666
azure-storage-resourcegroup = bla-blub

[cleanup.namespace.testns]
max-images-per-flavor = 42
azure-storage-resourcegroup = bla-blub-ns
""")
    provider = Provider('testns')
    assert provider.cfgGet('cleanup', 'max-images-per-flavor') == 42
    assert type(provider.cfgGet('cleanup', 'max-images-per-flavor')) is int
    assert provider.cfgGet('cleanup', 'azure-storage-resourcegroup') == 'bla-blub-ns'
    assert type(provider.cfgGet('cleanup', 'azure-storage-resourcegroup')) is str



def test_older_than_min_age_older(monkeypatch):
    monkeypatch.setattr(Provider, 'cfgGet', lambda *args, **kwargs: 24)
    provider = Provider('testolderminage')
    assert provider.older_than_min_age(datetime.now(timezone.utc) - timedelta(hours=25)) == True


def test_older_than_min_age_younger(monkeypatch):
    monkeypatch.setattr(Provider, 'cfgGet', lambda *args, **kwargs: 24)
    provider = Provider('testolderminage')
    assert provider.older_than_min_age(datetime.now(timezone.utc) - timedelta(hours=23)) == False


def test_needs_to_delete_image(monkeypatch):
    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
    provider = Provider('testneedstodelete')
    too_many_images = max_images_per_flavor+1
    not_enough_images = max_images_per_flavor-3
    older_than_min_age = datetime.now(timezone.utc) - timedelta(hours=min_image_age_hours+1)
    assert provider.needs_to_delete_image(too_many_images, datetime.now(timezone.utc)) == False
    assert provider.needs_to_delete_image(too_many_images, older_than_min_age) == True
    assert provider.needs_to_delete_image(not_enough_images, older_than_min_age) == False


def test_get_keeping_image_names(monkeypatch):
    monkeypatch.setattr(Provider, 'cfgGet', mock_cfgGet)
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
