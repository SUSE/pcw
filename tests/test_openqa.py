from unittest.mock import MagicMock, patch
import pytest
from openqa_client.const import JOB_STATE_CANCELLED
from openqa_client.exceptions import OpenQAClientError
from requests.exceptions import RequestException
from ocw.lib.openqa import OpenQA, get_url


@pytest.fixture
def openqa_client_mock():
    yield MagicMock()


@pytest.fixture
def openqa_instance(openqa_client_mock):
    with (
        patch('openqa_client.client.OpenQA_Client', return_value=openqa_client_mock),
        patch('ocw.lib.openqa.get_url', return_value=None)
    ):
        yield OpenQA(server="myserver")


def test_is_cancelled_returns_true_when_job_cancelled(openqa_instance, openqa_client_mock):
    job_id = "123"
    openqa_client_mock.openqa_request.return_value = {
        'job': {'state': JOB_STATE_CANCELLED}
    }

    result = openqa_instance.is_cancelled(job_id)
    assert result is True
    assert openqa_instance._OpenQA__client.openqa_request.call_count == 1


def test_is_cancelled_returns_false_when_job_not_cancelled(openqa_instance, openqa_client_mock):
    job_id = "124"
    openqa_client_mock.openqa_request.return_value = {
        'job': {'state': 'running'}
    }

    result = openqa_instance.is_cancelled(job_id)
    assert result is False
    assert openqa_instance._OpenQA__client.openqa_request.call_count == 1


def test_is_cancelled_raises_value_error_when_invalid_job_id(openqa_instance):
    invalid_job_id = "abc"

    with pytest.raises(ValueError):
        openqa_instance.is_cancelled(invalid_job_id)
    assert openqa_instance._OpenQA__client.openqa_request.call_count == 0


def test_is_cancelled_returns_false_when_request_errors_occurred(openqa_instance, openqa_client_mock):
    job_id = "125"
    openqa_client_mock.openqa_request.side_effect = OpenQAClientError()

    result = openqa_instance.is_cancelled(job_id)
    assert result is False


def test_singleton():
    with patch("requests.head"):
        osd = OpenQA(server="https://openqa.suse.de/")
        get_url.cache_clear()
        for url in ("https://openqa.suse.de", "https://openqa_suse_de", "openqa.suse.de", "openqa_suse_de"):
            osd2 = OpenQA(server="openqa.suse.de")
            assert osd2 is osd
            get_url.cache_clear()
        o3 = OpenQA(server="https://openqa.opensuse.org")
        assert osd is not o3
        get_url.cache_clear()


def test_get_url_cache():
    with patch("requests.head") as mock_head:
        url = get_url("https://openqa.suse.de/")
        url2 = get_url("https://openqa.suse.de")
        url3 = get_url("openqa.suse.de")
        assert url == url2 == url3
        assert mock_head.call_count == 1


def test_get_url_with_valid_scheme():
    url = get_url("https://openqa.suse.de")
    assert url == "https://openqa.suse.de"
    get_url.cache_clear()


def test_get_url_with_invalid_scheme():
    with patch("requests.head") as mock_head:
        mock_head.side_effect = OpenQAClientError
        with pytest.raises(OpenQAClientError):
            get_url("openqa.suse.de")
    get_url.cache_clear()


def test_get_url_with_valid_scheme_retry():
    with patch("requests.head") as mock_head:
        response_mock = mock_head.return_value
        response_mock.raise_for_status.side_effect = [RequestException, None]
        url = get_url("openqa.suse.de")
        assert url == "http://openqa.suse.de"
    get_url.cache_clear()


def test_get_url_with_invalid_server():
    with patch("requests.head") as mock_head:
        mock_head.side_effect = OpenQAClientError
        with pytest.raises(OpenQAClientError):
            get_url("invalid-openqa.suse.de")
    get_url.cache_clear()
