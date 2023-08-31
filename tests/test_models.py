from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import MagicMock
from ocw.models import Instance, CspInfo, format_seconds, StateChoice


@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    monkeypatch.setattr('openqa_client.client.OpenQA_Client', lambda *args, **kwargs: MagicMock())
    monkeypatch.setattr("ocw.lib.openqa.get_url", lambda x: x)


def test_format_seconds():
    # Test cases with different seconds values
    assert format_seconds(0) == "0s"
    assert format_seconds(59) == "59s"
    assert format_seconds(60) == "1m"
    assert format_seconds(65) == "1m5s"
    assert format_seconds(3600) == "1h"
    assert format_seconds(3665) == "1h1m5s"
    assert format_seconds(86400) == "1d"
    assert format_seconds(86465) == "1d1m5s"
    assert format_seconds(90061) == "1d1h1m1s"

    # Test case with a large value
    assert format_seconds(123456789) == "1428d21h33m9s"


@pytest.fixture
def example_instance_data():
    return {
        'provider': 'PROVIDER',
        'first_seen': datetime(2023, 1, 1, tzinfo=timezone.utc),
        'last_seen': datetime(2023, 1, 2, tzinfo=timezone.utc),
        'instance_id': 'INSTANCE_ID',
        'region': 'REGION',
        'namespace': 'NAMESPACE',
    }


@pytest.fixture
def example_cspinfo_data():
    return {
        'type': 'TYPE',
        'tags': '{"openqa_var_server": "http://example.com", "openqa_var_job_id": "12345", "openqa_var_name": "Test Job"}',
    }


@pytest.mark.django_db
def test_age_formatted(example_instance_data):
    instance = Instance.objects.create(**example_instance_data)

    # Set the age of the instance to 1 day (86400 seconds)
    instance.age = timedelta(days=1)
    instance.save()
    assert instance.age_formatted() == "1d"

    # Set the age of the instance to 2 hours (7200 seconds)
    instance.age = timedelta(hours=2)
    instance.save()
    assert instance.age_formatted() == "2h"

    # Set the age of the instance to 1 hour and 30 minutes (5400 seconds)
    instance.age = timedelta(hours=1, minutes=30)
    instance.save()
    assert instance.age_formatted() == "1h30m"

    # Set the age of the instance to 2 minutes and 15 seconds
    instance.age = timedelta(minutes=2, seconds=15)
    instance.save()
    assert instance.age_formatted() == "2m15s"

    # Test when the age is 0 seconds
    instance.age = timedelta(seconds=0)
    instance.save()
    assert instance.age_formatted() == "0s"


@pytest.mark.django_db
def test_ttl_formatted(example_instance_data):
    instance = Instance.objects.create(**example_instance_data)
    instance.ttl = timedelta(hours=3, minutes=30)
    assert instance.ttl_formatted() == "3h30m"


@pytest.mark.django_db
def test_ttl_expired(example_instance_data):
    instance = Instance.objects.create(**example_instance_data)
    assert not instance.ttl_expired()
    instance.age = timedelta(hours=5)
    instance.ttl = timedelta(hours=3)
    assert instance.ttl_expired()


@pytest.mark.django_db
def test_all_time_fields(example_instance_data):
    instance = Instance.objects.create(**example_instance_data)
    instance.age = timedelta(days=2, hours=5, minutes=30)
    instance.ttl = timedelta(hours=3, minutes=30)
    assert instance.all_time_fields() == "(age=2d5h30m, first_seen=2023-01-01 00:00, last_seen=2023-01-02 00:00, ttl=3h30m)"


@pytest.mark.django_db
def test_set_alive(example_instance_data, example_cspinfo_data):
    instance = Instance.objects.create(**example_instance_data)
    cspinfo = CspInfo.objects.create(instance=instance, **example_cspinfo_data)
    cspinfo.save()
    instance.set_alive()
    assert instance.last_seen is not None
    assert instance.active is True
    assert instance.age.total_seconds() > 0
    assert instance.state == StateChoice.ACTIVE


@pytest.mark.django_db
def test_get_type(example_instance_data, example_cspinfo_data):
    instance = Instance.objects.create(**example_instance_data)
    cspinfo = CspInfo.objects.create(instance=instance, **example_cspinfo_data)
    cspinfo.type = "TYPEX"
    cspinfo.save()
    assert instance.get_type() == "TYPEX"


@pytest.mark.django_db
def test_is_cancelled_without_tags(example_instance_data, example_cspinfo_data):
    instance = Instance.objects.create(**example_instance_data)
    cspinfo = CspInfo.objects.create(instance=instance, **example_cspinfo_data)
    cspinfo.save()
    # Test when both "openqa_var_job_id" and "openqa_var_server" tags are missing
    assert not instance.is_cancelled()


@pytest.mark.django_db
def test_is_cancelled_with_tags(example_instance_data, example_cspinfo_data, monkeypatch):
    instance = Instance.objects.create(**example_instance_data)
    cspinfo = CspInfo.objects.create(instance=instance, **example_cspinfo_data)

    # Mock the OpenQA class to return cancellation status
    class MockOpenQA:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def is_cancelled(job_id):
            return job_id == "12345"  # Pretend job_id "12345" is cancelled

    # Use monkeypatch to replace the original OpenQA class with the MockOpenQA class
    monkeypatch.setattr('ocw.models.OpenQA', MockOpenQA)

    # Test when "openqa_var_job_id" and "openqa_var_server" tags are present
    assert instance.is_cancelled()

    # Test when "openqa_var_job_id" is present, but "openqa_var_server" is missing
    cspinfo.tags = '{"openqa_var_job_id": "54321"}'
    cspinfo.save()
    assert not instance.is_cancelled()

    # Test when "openqa_var_server" is present, but "openqa_var_job_id" is missing
    cspinfo.tags = '{"openqa_var_server": "http://example.com"}'
    cspinfo.save()
    assert not instance.is_cancelled()


@pytest.mark.django_db
def test_get_openqa_job_link(example_instance_data, example_cspinfo_data):
    instance = Instance.objects.create(**example_instance_data)
    cspinfo = CspInfo.objects.create(instance=instance, **example_cspinfo_data)

    # Test when both "openqa_var_server" and "openqa_var_job_id" tags are present
    link = cspinfo.get_openqa_job_link()
    assert link is not None
    assert link['url'] == "http://example.com/t12345"
    assert link['title'] == "Test Job"

    # Test when only "openqa_var_server" tag is present
    cspinfo.tags = '{"openqa_var_server": "http://example.com"}'
    cspinfo.save()
    link = cspinfo.get_openqa_job_link()
    assert link is None

    # Test when only "openqa_var_job_id" tag is present
    cspinfo.tags = '{"openqa_var_job_id": "12345"}'
    cspinfo.save()
    link = cspinfo.get_openqa_job_link()
    assert link is None

    # Test when both "openqa_var_server" and "openqa_var_job_id" tags are missing
    cspinfo.tags = '{}'
    cspinfo.save()
    link = cspinfo.get_openqa_job_link()
    assert link is None


@pytest.mark.django_db
def test_get_tag(example_instance_data, example_cspinfo_data):
    instance = Instance.objects.create(**example_instance_data)
    cspinfo = CspInfo.objects.create(instance=instance, **example_cspinfo_data)

    assert cspinfo.get_tag('openqa_var_server') == "http://example.com"
    assert cspinfo.get_tag('openqa_var_job_id') == "12345"
    assert cspinfo.get_tag('openqa_var_name') == "Test Job"
    assert cspinfo.get_tag('non_existent_tag') is None
    assert cspinfo.get_tag('non_existent_tag', default_value="N/A") == "N/A"
