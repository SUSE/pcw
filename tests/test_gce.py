import httplib2
from googleapiclient.errors import HttpError
from pytest import fixture, mark, raises
from unittest.mock import MagicMock, patch
import json
from datetime import datetime, timezone, timedelta
from ocw.lib.gce import GCE
from webui.PCWConfig import PCWConfig
from tests.generators import max_age_hours, mock_get_feature_property


class MockRequest:
    def __init__(self, response=None, error_reason=None):
        if response is None:
            response = {}
        self.response = response
        self.error_reason = error_reason

    def execute(self):
        if self.error_reason:
            content = bytes(json.dumps({"error": {"errors": [{"reason": self.error_reason}]}}), 'utf-8')
            raise HttpError(httplib2.Response({'status': 200}), content)
        return self.response


class MockResource:

    def __init__(self, responses):
        self.deleted_resources = list()
        self.responses = responses
        self.error_reason = None

    def __call__(self, *args, **kwargs):
        return self

    def list(self, *args, **kwargs):
        return self.responses.pop(0)

    def list_next(self, *args, **kwargs):
        return self.responses.pop(0)

    def delete(self, *args, **kwargs):
        for resource in ('object', 'image', 'disk', 'instance', 'firewall', 'forwardingRule', 'route', 'network', 'subnetwork'):
            if resource in kwargs:
                if self.error_reason:
                    return MockRequest(error_reason=self.error_reason)
                self.deleted_resources.append(kwargs[resource])
                if len(self.responses) > 0:
                    return self.responses.pop(0)
                return MockRequest(None)
        raise ValueError("Unexpected delete request")

    def get(self, project, region):
        def something():
            pass
        something.execute = lambda: self.responses
        return something


class MockClient:
    def objects(self): pass
    def disks(self): pass
    def firewalls(self): pass
    def forwardingRules(self): pass
    def images(self): pass
    def instances(self): pass
    def networks(self): pass
    def routes(self): pass
    def subnetworks(self): pass


@fixture
def gce():
    with (
        patch.object(PCWConfig, 'get_feature_property', new=mock_get_feature_property),
        patch.object(GCE, 'get_data', return_value={"project_id": "project"}),
        patch.object(GCE, 'read_auth_json', return_value={}),
    ):
        gce = GCE('fake')
        gce.storage_client = MockClient
        gce.compute_client = MockClient
        gce.compute_client.instances = MockResource([MockRequest({'items': ['instance1', 'instance2']}), None])
        yield gce


@fixture
def gce_dry_run_false(gce):
    gce.dry_run = False
    with (
        patch.object(gce, 'list_regions', return_value=['region1']),
        patch.object(gce, 'list_zones', return_value=['zone1'])
    ):
        yield gce


@fixture
def mocked_resource():
    older_than_max_age = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours+1)).strftime("%m/%d/%Y, %H:%M:%S")
    now_age = datetime.now(timezone.utc).strftime("%m/%d/%Y, %H:%M:%S")
    return MockResource([
        MockRequest({   # on images().list()
            'items': [
                {'name': 'keep', 'creationTimestamp': now_age, 'timeCreated': now_age, 'network': 'mynetwork'},
                {'name': 'delete1', 'creationTimestamp': older_than_max_age, 'timeCreated': older_than_max_age, 'network': 'mynetwork'}
            ], 'id': "id"}),
        MockRequest(),  # on images().delete()
        MockRequest({   # on images().list_next()
            'items': [
                {'name': 'keep', 'creationTimestamp': now_age, 'timeCreated': now_age, 'network': 'mynetwork'},
                {'name': 'delete2', 'creationTimestamp': older_than_max_age, 'timeCreated': older_than_max_age, 'network': 'mynetwork'}
            ], 'id': "id"}),
        MockRequest({'error': {'errors': [{'message': 'err message'}]},
                    'warnings': [{'message': 'warning message'}]}),
        None   # on images().list_next()
    ])


def test_delete_instance(gce):
    instances = MockResource([MockRequest({'items': ['instance1', 'instance2']}), None])
    gce.compute_client.instances = instances
    gce.delete_instance("instance1", "zone1")
    assert instances.deleted_resources == ["instance1"]


def test_list_instances(gce):
    assert gce.list_instances(zone="zone1") == ["instance1", "instance2"]


def test_list_all_instances(gce):
    with (
        patch.object(gce, "list_regions", return_value=["region1"]),
        patch.object(gce, "list_zones", return_value=["zone1"]),
    ):
        assert gce.list_all_instances() == ["instance1", "instance2"]


def test_list_regions(gce):
    gce.compute_client.regions = MockResource([MockRequest({'items': [{'name': 'Wonderland'}]}), None])
    assert gce.list_regions() == ['Wonderland']


def test_list_zones(gce):
    gce.compute_client.regions = MockResource({'zones': ['somethingthatIdonotknow/RabbitHole']})
    gce.compute_client.list_zones = {'zones': ['somethingthatIdonotknow/RabbitHole']}
    assert gce.list_zones('Oxfordshire') == ['RabbitHole']


def _test_cleanup(gce, resource_type, cleanup_call, resources):

    with (
        patch.object(gce, 'list_regions', return_value=['region1']),
        patch.object(gce, 'list_zones', return_value=['zone1']),
    ):
        setattr(gce.compute_client, resource_type, resources)
        setattr(gce.storage_client, resource_type, resources)
        cleanup_call()
        if gce.dry_run:
            assert resources.deleted_resources == []
        else:
            assert resources.deleted_resources == ['delete1', 'delete2']


@mark.parametrize("dry_run", [True, False])
def test_cleanup_blobs(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "objects", gce.cleanup_blobs, mocked_resource)


@mark.parametrize("dry_run", [True, False])
def test_cleanup_disks(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "disks", gce.cleanup_disks, mocked_resource)


@mark.parametrize("dry_run", [True, False])
def test_cleanup_images(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "images", gce.cleanup_images, mocked_resource)


@mark.parametrize("dry_run", [True, False])
def test_cleanup_firewalls(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "firewalls", gce.cleanup_firewalls, mocked_resource)


@mark.parametrize("dry_run", [True, False])
def test_cleanup_forwarding_rules(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "forwardingRules", gce.cleanup_forwarding_rules, mocked_resource)


@mark.parametrize("dry_run", [True, False])
def test_cleanup_routes(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "routes", gce.cleanup_routes, mocked_resource)


def test_cleanup_routes_delete_default_route_raise_exception(gce_dry_run_false, mocked_resource):
    setattr(gce_dry_run_false.compute_client, "routes", mocked_resource)
    with raises(HttpError):
        mocked_resource.error_reason = "unknown"
        gce_dry_run_false.cleanup_routes()


@mark.parametrize("mocked_resource_reason", ["resourceInUseByAnotherResource", "badRequest"])
def test_cleanup_routes_delete_default_route_not_raise_exception(gce_dry_run_false, mocked_resource, mocked_resource_reason):
    setattr(gce_dry_run_false.compute_client, "routes", mocked_resource)
    mocked_resource.error_reason = mocked_resource_reason
    gce_dry_run_false.cleanup_routes()


@mark.parametrize("dry_run", [True, False])
def test_cleanup_subnetworks(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "subnetworks", gce.cleanup_subnetworks, mocked_resource)


@mark.parametrize("dry_run", [True, False])
def test_cleanup_networks(gce, mocked_resource, dry_run):
    gce.dry_run = dry_run
    _test_cleanup(gce, "networks", gce.cleanup_networks, mocked_resource)


def test_cleanup_all(gce):
    gce.cleanup_blobs = MagicMock()
    gce.cleanup_disks = MagicMock()
    gce.cleanup_images = MagicMock()
    gce.cleanup_firewalls = MagicMock()
    gce.cleanup_forwarding_rules = MagicMock()
    gce.cleanup_routes = MagicMock()
    gce.cleanup_subnetworks = MagicMock()
    gce.cleanup_networks = MagicMock()
    gce.cleanup_all()
    gce.cleanup_disks.assert_called_once()
    gce.cleanup_images.assert_called_once()
    gce.cleanup_firewalls.assert_called_once()
    gce.cleanup_forwarding_rules.assert_called_once()
    gce.cleanup_routes.assert_called_once()
    gce.cleanup_networks.assert_called_once()
    gce.cleanup_subnetworks.assert_called_once()


def test_get_error_reason():

    class MockHttpError:
        def __init__(self, content) -> None:
            self.content = json.dumps(content) if content is not None else ""

    assert GCE.get_error_reason(MockHttpError(content=None)) == "unknown"
    assert GCE.get_error_reason(MockHttpError({})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {}})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {'errors': []}})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {'errors': [{}]}})) == "unknown"
    assert GCE.get_error_reason(MockHttpError({'error': {'errors': [{'reason': 'aaa'}]}})) == "aaa"
