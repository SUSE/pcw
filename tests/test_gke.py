from ocw.lib.gke import GKE
from ocw.lib.gce import GCE
from ocw.lib.provider import Provider
import pytest
import kubernetes
from tests.kubernetes import MockedKubernetesClient, MockedKubernetesConfig
from tests.kubernetes import MockedKubernetesJob, MockedKubernetesNamespace


@pytest.fixture
def k8s_patch(monkeypatch):
    monkeypatch.setattr(Provider, 'read_auth_json', lambda *args, **kwargs: '{}')
    monkeypatch.setattr(GCE, 'get_data', lambda *args, **kwargs: {"project_id": "project"})
    monkeypatch.setattr(GKE, 'list_zones', lambda *args, **kwargs: ["zone"])
    monkeypatch.setattr(GKE, 'list_regions', lambda *args, **kwargs: ["region"])
    monkeypatch.setattr(GKE, 'get_clusters', lambda *args, **kwargs: [{"name": "cluster"}])

    return GKE('fake')


def test_cleanup_k8s_jobs(k8s_patch, monkeypatch):
    monkeypatch.setattr(kubernetes, 'config', MockedKubernetesConfig())
    mocked_kubernetes = MockedKubernetesClient(jobs=[MockedKubernetesJob("job1", 1), MockedKubernetesJob("job2", 0)])
    monkeypatch.setattr(kubernetes, 'client', mocked_kubernetes)
    monkeypatch.setattr(GKE, 'kubectl_client', lambda *args, **kwargs: mocked_kubernetes)
    k8s_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 1
    assert mocked_kubernetes.deleted_jobs[0] == "job1"

    # test dry_run
    k8s_patch.dry_run = True
    mocked_kubernetes.deleted_jobs = []
    k8s_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 0


def test_cleanup_k8s_namespaces(k8s_patch, monkeypatch):
    monkeypatch.setattr(kubernetes, 'config', MockedKubernetesConfig())
    mocked_kubernetes = MockedKubernetesClient(namespaces=[
        MockedKubernetesNamespace("helm-test-234", 1),  # good name, too fresh
        MockedKubernetesNamespace("helm-test-342", 9),  # good name, old enough
        MockedKubernetesNamespace("kube-system", 9),  # bad name
        MockedKubernetesNamespace("something-else-745", 9)  # bad name
    ])
    monkeypatch.setattr(kubernetes, 'client', mocked_kubernetes)
    monkeypatch.setattr(GKE, 'kubectl_client', lambda *args, **kwargs: mocked_kubernetes)
    assert len(mocked_kubernetes.list_namespace().items) == 4

    k8s_patch.cleanup_k8s_namespaces()
    assert len(mocked_kubernetes.deleted_namespaces) == 1
    assert mocked_kubernetes.deleted_namespaces[0] == "helm-test-342"

    # test dry_run
    k8s_patch.dry_run = True
    mocked_kubernetes.deleted_namespaces = []
    k8s_patch.cleanup_k8s_namespaces()
    assert len(mocked_kubernetes.deleted_namespaces) == 0
