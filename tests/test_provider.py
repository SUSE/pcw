from ocw.lib.provider import Provider
from datetime import datetime
from datetime import timezone
from datetime import timedelta
from tests import generators
from webui.settings import PCWConfig
from .generators import mock_get_feature_property
from .generators import max_age_hours
import pytest


@pytest.fixture
def provider_patch(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda *args, **kwargs: 24)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')


def test_older_than_max_age_hours_older(provider_patch):
    provider = Provider('testolderminage')
    assert provider.is_outdated(datetime.now(timezone.utc) - timedelta(hours=25)) == True


def test_older_than_max_age_hours_younger(provider_patch):
    provider = Provider('testolderminage')
    assert provider.is_outdated(datetime.now(timezone.utc) - timedelta(hours=23)) == False


def test_getData(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: {"param1": "value1"})
    provider = Provider('testneedstodelete')

    assert provider.getData() == {'param1': 'value1'}
    assert provider.getData('param1') == 'value1'
