from ocw.lib.provider import Provider
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from webui.settings import PCWConfig
from .generators import mock_get_feature_property
import pytest


@pytest.fixture
def provider_patch(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda *args, **kwargs: 24)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')


def test_older_than_max_age_hours_older(provider_patch):
    provider = Provider('testolderminage')
    assert provider.is_outdated(datetime.now(timezone.utc) - timedelta(hours=25)) is True


def test_older_than_max_age_hours_younger(provider_patch):
    provider = Provider('testolderminage')
    assert provider.is_outdated(datetime.now(timezone.utc) - timedelta(hours=23)) is False


def test_get_data(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: {"param1": "value1"})
    provider = Provider('testneedstodelete')

    assert provider.get_data() == {'param1': 'value1'}
    assert provider.get_data('param1') == 'value1'


def test_exec_cmd(provider_patch):
    provider = Provider('testexeccmd')
    out = provider.cmd_exec("echo 'test'")
    assert out.returncode == 0

    out = provider.cmd_exec("ls /invalid_dir")
    assert out.returncode != 0
