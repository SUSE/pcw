from ocw.lib.gce import GCE, Provider
from webui.PCWConfig import PCWConfig
from tests.generators import max_age_hours, mock_get_feature_property
from datetime import datetime, timezone, timedelta


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


def test_cleanup_all(monkeypatch):
    older_than_max_age = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours+1)).strftime("%m/%d/%Y, %H:%M:%S")
    now_age = datetime.now(timezone.utc).strftime("%m/%d/%Y, %H:%M:%S")

    fmi = FakeMockImages([
        FakeRequest({   # on images().list()
            'items': [
                {'name': 'keep', 'creationTimestamp': now_age},
                {'name': 'delete1', 'creationTimestamp': older_than_max_age}
            ]
        }),
        FakeRequest(),    # on images().delete()
        FakeRequest({   # on images().list_next()
            'items': [
                {'name': 'keep', 'creationTimestamp': now_age},
                {'name': 'delete2', 'creationTimestamp': older_than_max_age}
            ]
        }),
        FakeRequest({'error': {'errors': [{'message': 'err message'}]},
                    'warnings': [{'message': 'warning message'}]}),
        None   # on images().list_next()
    ])

    def mocked_compute_client():
        pass
    mocked_compute_client.images = lambda *args, **kwargs: fmi
    monkeypatch.setattr(GCE, 'compute_client', lambda self: mocked_compute_client)
    monkeypatch.setattr(GCE, 'get_data', lambda *args, **kwargs: {"project_id": "project"})
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')

    gce = GCE('fake')
    gce.cleanup_all()
    assert fmi.deleted == ['delete1', 'delete2']

    fmi = FakeMockImages([FakeRequest({})])
    gce.cleanup_all()
    assert fmi.deleted == []
