import pytest
from ocw.lib.gce import GCE
from webui.settings import PCWConfig
from tests.generators import min_image_age_hours, max_image_age_hours
from tests import generators
from datetime import datetime, timezone, timedelta


@pytest.fixture
def gce_provider_patched(monkeypatch):
    from tests.generators import mock_get_feature_property

    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    return monkeypatch


def test_parse_image_name(monkeypatch):
    monkeypatch.setattr(PCWConfig, 'get_feature_property', lambda *args, **kwargs: "FOOF")
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

    assert gce.parse_image_name('sles15-sp2-chost-byos-x8664-0-9-3-gce-build1-11') == {
            'key': '15-sp2-gce-chost-byos-x8664',
            'build': '0-9-3-1-11'
            }

    assert gce.parse_image_name('do not match') is None


class FakeRequest:
    def __init__(self, response={}):
        self.response = response

    def execute(self):
        return self.response


class FakeMockImages:

    def __init__(self, responses):
        self.deleted = list()
        self.responses = responses

    def list(self, *args, **kwargs):
        return self.responses.pop(0)

    def list_next(self, *args, **kwargs):
        return self.responses.pop(0)

    def delete(self, *args, **kwargs):
        self.deleted.append(kwargs['image'])
        return self.responses.pop(0)


class FakeServiceAccounts:

    def __init__(self, responses):
        self.deleted = list()
        self.responses = responses

    def list(self, *args, **kwargs):
        return self.responses.pop(0)

    def list_next(self, *args, **kwargs):
        return None

    def delete(self, *args, **kwargs):
        pass

    def keys(self,  *args, **kwargs):
        return self.responses


def test_cleanup_all(gce_provider_patched):
    newer_then_min_age = datetime.now(timezone.utc).isoformat()
    older_then_min_age = (datetime.now(timezone.utc) - timedelta(hours=min_image_age_hours+1)).isoformat()
    older_then_max_age = (datetime.now(timezone.utc) - timedelta(hours=max_image_age_hours+1)).isoformat()

    fmi = FakeMockImages([
        FakeRequest({   # on images().list()
            'items': [
                {'name': 'I will not be parsed', 'creationTimestamp': older_then_max_age},
                {'name': 'sles12-sp5-gce-x8664-0-9-1-byos-build1-54', 'creationTimestamp': newer_then_min_age},
                {'name': 'sles12-sp5-gce-x8664-0-9-1-byos-build1-56', 'creationTimestamp': older_then_min_age}
            ]
        }),
        FakeRequest({   # on images().list_next()
            'items': [
                {'name': 'sles12-sp5-gce-x8664-0-9-1-byos-build1-57', 'creationTimestamp': older_then_min_age},
                {'name': 'sles12-sp5-gce-x8664-0-9-1-byos-build1-58', 'creationTimestamp': older_then_max_age}
            ]
        }),
        None,   # on images().list_next()
        FakeRequest({'error': {'errors': [{'message': 'err message'}]}, 'warnings': [{'message': 'warning message'}]}),
        FakeRequest(),    # on images().delete()
        ])

    def mocked_compute_client():
        pass

    mocked_compute_client.images = lambda *args, **kwargs: fmi
    gce_provider_patched.setattr(GCE, 'compute_client', lambda self: mocked_compute_client)
    # Skips cleanup_serviceaccounts
    gce_provider_patched.setattr(GCE, 'cleanup_serviceaccounts', lambda self: True)

    gce = GCE('fake')
    generators.max_images_per_flavor = 2
    gce.cleanup_all()
    assert fmi.deleted == ['sles12-sp5-gce-x8664-0-9-1-byos-build1-56', 'sles12-sp5-gce-x8664-0-9-1-byos-build1-58']

    fmi = FakeMockImages([FakeRequest({})])
    gce.cleanup_all()
    assert fmi.deleted == []


def test_get_service_accounts(gce_provider_patched):
    expected = ["vaultopenqa-role3-1111@suse-sle-qa.iam.test.com",
                "vaultopenqa-role3-2222@suse-sle-qa.iam.test.com",
                "vaultopenqa-role3-3333@suse-sle-qa.iam.test.com"]

    fake_vault_service_accounts = FakeServiceAccounts([
        FakeRequest({   # on serviceAccounts().list()
            "accounts": [
                {"name": "projects/suse-sle-qa/serviceAccounts/vaultopenqa-role3-1111@suse-sle-qa.iam.test.com",
                 "email": "vaultopenqa-role3-1111@suse-sle-qa.iam.test.com"},
                {"name": "projects/suse-sle-qa/serviceAccounts/vaultopenqa-role3-2222@suse-sle-qa.iam.test.com",
                 "email": "vaultopenqa-role3-2222@suse-sle-qa.iam.test.com"},
                {"name": "projects/suse-sle-qa/serviceAccounts/vaultopenqa-role3-3333@suse-sle-qa.iam.test.com",
                 "email": "vaultopenqa-role3-3333@suse-sle-qa.iam.test.com"},
            ]
        })
    ])

    def mocked_iam_client():
        return FakeServiceAccounts()

    gce_provider_patched.setattr(GCE, 'iam_client', lambda self: mocked_iam_client)

    mocked_iam_client.projects = lambda *args, **kwargs: mocked_iam_client
    mocked_iam_client.serviceAccounts = lambda *args, **kwargs: fake_vault_service_accounts

    gce = GCE("fake")
    actual = gce.get_service_accounts()
    assert sorted(actual) == expected


def test_delete_service_accounts_with(gce_provider_patched):

    def mocked_iam_client():
        return FakeServiceAccounts()

    gce_provider_patched.setattr(GCE, 'iam_client', lambda self: mocked_iam_client)

    mocked_iam_client.projects = lambda *args, **kwargs: mocked_iam_client
    mocked_iam_client.serviceAccounts = lambda *args, **kwargs: mocked_iam_client

    usermails = [
            "vaultopenqa-role-1111@suse-sle-qa.iam.gserviceaccount.com",
            "vaultopenqa-role-1111@suse-sle-qa.iam.gserviceaccount.com",
        ]
    mocked_iam_client.delete = lambda self: usermails

    gce = GCE("fake")
    gce.delete_service_accounts(usermails)
