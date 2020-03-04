from ocw.lib.provider import Provider
from pathlib import Path, PurePath
import webui
from datetime import datetime
from datetime import timezone
from datetime import timedelta

working_dir = Path(PurePath(Path(__file__).absolute()).parent)
webui.settings.CONFIG_FILE = working_dir / 'pcw_test_provider.ini'
min_image_age_hours = 7
max_images_per_flavor = 10
max_image_age_hours = 20


def set_pcw_ini(add=''):
    with open(webui.settings.CONFIG_FILE, "w") as f:
        f.write(add)


def mock_cfgGet(self, section, field):
    if field == 'min-image-age-hours':
        return min_image_age_hours
    elif field == 'max-images-per-flavor':
        return max_images_per_flavor
    elif field == 'max-image-age-hours':
        return max_image_age_hours


def test_cfgGet_with_defaults():
    set_pcw_ini()
    provider = Provider('testns')
    assert provider.cfgGet('cleanup', 'max-images-per-flavor') == 1
    assert type(provider.cfgGet('cleanup', 'max-images-per-flavor')) is int
    assert provider.cfgGet('cleanup', 'azure-storage-resourcegroup') == 'openqa-upload'
    assert type(provider.cfgGet('cleanup', 'azure-storage-resourcegroup')) is str


def test_cfgGet_from_pcw_ini():
    set_pcw_ini("""
[cleanup]
max-images-per-flavor = 666
azure-storage-resourcegroup = bla-blub
""")
    provider = Provider('testns')
    assert provider.cfgGet('cleanup', 'max-images-per-flavor') == 666
    assert type(provider.cfgGet('cleanup', 'max-images-per-flavor')) is int
    assert provider.cfgGet('cleanup', 'azure-storage-resourcegroup') == 'bla-blub'
    assert type(provider.cfgGet('cleanup', 'azure-storage-resourcegroup')) is str


def test_cfgGet_from_pcw_ini_with_namespace():
    set_pcw_ini("""
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


def test_cleanup_pcw_ini():
    Path(webui.settings.CONFIG_FILE).unlink()


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
