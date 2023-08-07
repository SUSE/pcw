import pytest
import kubernetes
from ocw.lib.provider import Provider
from ocw.lib.aks import AKS
from webui.PCWConfig import PCWConfig
from tests.kubernetes import MockedSubprocessReturn, MockedKubernetesClient, MockedKubernetesConfig
from tests.kubernetes import MockedKubernetesJob, MockedKubernetesNamespace


class MockedAKSCluster():
    def __init__(self, name):
        self.name = name


@pytest.fixture
def aks_patch(monkeypatch):
    monkeypatch.setattr(Provider, 'read_auth_json',
                        lambda *args, **kwargs: {'client_id': 'key', 'client_secret': 'secret',
                                                 'subscription_id': 'subscription', 'tenant_id': 'tenant',
                                                 'resource_group_name': 'group'})
    monkeypatch.setattr(kubernetes, 'config', MockedKubernetesConfig())
    return AKS('fake')


def test_kubectl_client(aks_patch, monkeypatch):
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(0))
    mocked_client1 = MockedKubernetesClient(1)
    monkeypatch.setattr(kubernetes, 'client', mocked_client1)

    assert aks_patch.kubectl_client("group", "cluster") == mocked_client1

    # Check that the client is reused
    mocked_client2 = MockedKubernetesClient(1)
    monkeypatch.setattr(kubernetes, 'client', mocked_client2)
    assert aks_patch.kubectl_client("group", "cluster") == mocked_client1


def test_cleanup_k8s_jobs(aks_patch, monkeypatch):
    mocked_kubernetes = MockedKubernetesClient([MockedKubernetesJob("job1", 1), MockedKubernetesJob("job2", 0)])
    monkeypatch.setattr(AKS, "kubectl_client", lambda *args, **kwargs: mocked_kubernetes)
    monkeypatch.setattr(PCWConfig, "get_k8s_clusters_for_provider", lambda *args, **kwargs: [
        {'resource_group': 'group', 'cluster_name': 'cluster'}])
    aks_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 1
    assert mocked_kubernetes.deleted_jobs[0] == "job1"

    # test dry_run
    aks_patch.dry_run = True
    mocked_kubernetes.deleted_jobs = []
    aks_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 0


def test_cleanup_k8s_namespaces(aks_patch, monkeypatch):
    mocked_kubernetes = MockedKubernetesClient(namespaces=[
        MockedKubernetesNamespace("helm-test-234", 1),  # good name, too fresh
        MockedKubernetesNamespace("helm-test-342", 9),  # good name, old enough
        MockedKubernetesNamespace("kube-system", 9),  # bad name
        MockedKubernetesNamespace("something-else-745", 9)  # bad name
    ])
    monkeypatch.setattr(AKS, "kubectl_client", lambda *args, **kwargs: mocked_kubernetes)
    monkeypatch.setattr(PCWConfig, "get_k8s_clusters_for_provider", lambda *args, **kwargs: [
        {'resource_group': 'group', 'cluster_name': 'cluster'}])
    assert len(mocked_kubernetes.list_namespace().items) == 4

    aks_patch.cleanup_k8s_namespaces()
    assert len(mocked_kubernetes.deleted_namespaces) == 1
    assert mocked_kubernetes.deleted_namespaces[0] == "helm-test-342"

    # test dry_run
    aks_patch.dry_run = True
    mocked_kubernetes.deleted_namespaces = []
    aks_patch.cleanup_k8s_namespaces()
    assert len(mocked_kubernetes.deleted_namespaces) == 0
