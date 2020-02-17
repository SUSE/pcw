from ocw.lib.gce import GCE
from webui.settings import ConfigFile


def test_parse_image_name(monkeypatch):
    monkeypatch.setattr(ConfigFile, 'get', lambda *args, **kwargs: "FOOF")
    gce = GCE('fake')

    assert gce.parse_image_name('sles12-sp5-gce-x8664-0-9-1-byos-build1-56') == {
            'key': '12-sp5-gce-byos-x8664',
            'build': '0-9-1-1-56'
            }

    assert gce.parse_image_name('sles15-sp2-byos-x8664-0-9-3-gce-build1-10') == {
            'key': '15-sp2-gce-byos-x8664',
            'build': '0-9-3-1-10'
            }

    assert gce.parse_image_name('sles15-sp2-x8664-0-9-3-gce-build1-10') == {
            'key': '15-sp2-gce-x8664',
            'build': '0-9-3-1-10'
            }

    assert gce.parse_image_name('do not match') is None
