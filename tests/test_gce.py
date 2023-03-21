import json
from datetime import datetime, timezone, timedelta
from ocw.lib.gce import GCE, Provider
from webui.PCWConfig import PCWConfig
from tests.generators import max_age_hours, mock_get_feature_property


class FakeRequest:
    def __init__(self, response={}):
        self.response = response

    def execute(self):
        return self.response


class FakeMockRegions:
    def __init__(self, responses):
        self.responses = responses

    def list(self, *args, **kwargs):
        return self.responses.pop(0)

    def list_next(self, *args, **kwargs):
        return self.responses.pop(0)

    def get(self, project, region):
        def something():
            pass
        something.execute = lambda: self.responses
        return something


def test_list_regions(monkeypatch):
    def mocked_compute_client():
        pass
    fmr = FakeMockRegions([FakeRequest({'items': [{'name': 'Wonderland'}]}), None])
    mocked_compute_client.regions = lambda *args, **kwargs: fmr
    monkeypatch.setattr(GCE, 'compute_client', lambda self: mocked_compute_client)
    monkeypatch.setattr(GCE, 'get_data', lambda *args, **kwargs: {"project_id": "project"})
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    gce = GCE('fake')
    assert gce.list_regions() == ['Wonderland']


def test_list_zones(monkeypatch):
    def mocked_compute_client():
        pass
    fmr = FakeMockRegions({'zones': ['somethingthatIdonotknow/RabbitHole']})
    mocked_compute_client.regions = lambda *args, **kwargs: fmr
    monkeypatch.setattr(GCE, 'compute_client', lambda self: mocked_compute_client)
    monkeypatch.setattr(GCE, 'get_data', lambda *args, **kwargs: {"project_id": "project"})
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    gce = GCE('fake')
    assert gce.list_zones('Oxfordshire') == ['RabbitHole']


class FakeMockImages:
    def __init__(self, responses):
        self.deleted_images = list()
        self.deleted_disks = list()
        self.responses = responses

    def list(self, *args, **kwargs):
        return self.responses.pop(0)

    def list_next(self, *args, **kwargs):
        return self.responses.pop(0)

    def delete(self, *args, **kwargs):
        if 'image' in kwargs:
            self.deleted_images.append(kwargs['image'])
        elif 'disk' in kwargs:
            self.deleted_disks.append(kwargs['disk'])
        else:
            raise ValueError("Unexpected delete request")
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

    fmd = FakeMockImages([
        FakeRequest({   # on disks().list()
            'items': [
                {'name': 'keep', 'creationTimestamp': now_age},
                {'name': 'delete_disk1', 'creationTimestamp': older_than_max_age}
            ]
        }),
        FakeRequest(),    # on disks().delete()
        FakeRequest({   # on disks().list_next()
            'items': [
                {'name': 'keep', 'creationTimestamp': now_age},
                {'name': 'delete_disk2', 'creationTimestamp': older_than_max_age}
            ]
        }),
        FakeRequest({'error': {'errors': [{'message': 'err message'}]},
                    'warnings': [{'message': 'warning message'}]}),
        None   # on disks().list_next()
    ])

    def mocked_compute_client():
        pass
    mocked_compute_client.images = lambda *args, **kwargs: fmi
    mocked_compute_client.disks = lambda *args, **kwargs: fmd
    monkeypatch.setattr(GCE, 'compute_client', lambda self: mocked_compute_client)
    monkeypatch.setattr(GCE, 'get_data', lambda *args, **kwargs: {"project_id": "project"})
    monkeypatch.setattr(GCE, 'list_regions', lambda *args, **kwargs: ['region1'])
    monkeypatch.setattr(GCE, 'list_zones', lambda *args, **kwargs: ['zone1'])
    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')

    gce = GCE('fake')
    gce.cleanup_all()
    assert fmi.deleted_images == ['delete1', 'delete2']
    assert fmd.deleted_disks == ['delete_disk1', 'delete_disk2']


def test_get_error_reason():

    class MockHttpError:

        def __init__(self, content) -> None:
            if content is not None:
                self.content = json.dumps(content)
            else:
                self.content = ""

    assert GCE.get_error_reason(MockHttpError(content=None)) == "unknown"
    assert GCE.get_error_reason(MockHttpError({})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {}})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {'errors': []}})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {'errors': [{}]}})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {'errors': [{'reason': 'aaa'}]}})) == "aaa"
