from ocw.lib.provider import Provider
from pathlib import Path, PurePath
import webui

working_dir = Path(PurePath(Path(__file__).absolute()).parent)
webui.settings.CONFIG_FILE = working_dir / 'pcw_test_provider.ini'


def set_pcw_ini(add=''):
    with open(webui.settings.CONFIG_FILE, "w") as f:
        f.write(add)


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
