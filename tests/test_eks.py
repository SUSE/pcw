import os
from datetime import datetime, timezone, timedelta
import pytest
import kubernetes
from ocw.lib.provider import Provider
from ocw.lib.eks import EKS
from webui.PCWConfig import PCWConfig
from tests.generators import mock_get_feature_property


def test_list_clusters(eks_patch, monkeypatch):
    mocked_eks = MockedEKSClient()
    monkeypatch.setattr(EKS, 'eks_client', lambda self, region: mocked_eks)
    all_clusters = eks_patch.all_clusters()
    assert all_clusters == {}

    mocked_eks.clusters_list = {'clusters': ['empty']}
    all_clusters = eks_patch.all_clusters()
    assert all_clusters == {}

    mocked_eks.clusters_list = {'clusters': ['hascluster']}
    all_clusters = eks_patch.all_clusters()
    assert all_clusters == {}

    mocked_eks.clusters_list = {'clusters': ['hastags']}
    all_clusters = eks_patch.all_clusters()
    assert all_clusters == {'region1': ['hastags']}

    mocked_eks.clusters_list = {'clusters': ['hastags', 'ignored']}
    all_clusters = eks_patch.all_clusters()
    assert all_clusters == {'region1': ['hastags']}


class MockedEKSClient():
    def __init__(self):
        self.clusters_list = []

    def list_clusters(self):
        return self.clusters_list

    def describe_cluster(self, name=None):
        if name == 'empty':
            return {}
        elif name == 'hascluster':
            return {'cluster': {}}
        elif name == 'hastags':
            return {'cluster': {'tags': {}}}
        elif name == 'ignored':
            return {'cluster': {'tags': {'pcw_ignore': '1'}}}
        return None


class MockedKubernetesConfig():
    def load_kube_config(self, *args, **kwargs):
        return True


class MockedKubernetesClient():
    def __init__(self, jobs=[]):
        self.jobs = jobs
        self.deleted_jobs = []

    # pylint: disable=C0103
    def BatchV1Api(self):
        return self

    def list_job_for_all_namespaces(self, *args, **kwargs):
        return MockedKubernetesResult(self.jobs)

    def delete_namespaced_job(self, name, namespace):
        self.deleted_jobs.append(name)


class MockedKubernetesResult():
    def __init__(self, items):
        self.items = items


class MockedKubernetesJobStatus():
    def __init__(self, age):
        self.start_time = datetime.now(timezone.utc) - timedelta(days=age)


class MockedKubernetesJobMetadata():
    def __init__(self, name):
        self.name = name
        self.namespace = "default"


class MockedKubernetesJob():
    def __init__(self, name, age):
        self.status = MockedKubernetesJobStatus(age)
        self.metadata = MockedKubernetesJobMetadata(name)


class MockedSubprocessReturn():
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout


@pytest.fixture
def eks_patch(monkeypatch):
    def mocked_cmd_exec(self, cmd):
        if "describe-regions" in cmd:
            return MockedSubprocessReturn(stdout="[\"region1\"]")
        return MockedSubprocessReturn(0)

    monkeypatch.setattr(PCWConfig, 'get_feature_property', mock_get_feature_property)
    monkeypatch.setattr(Provider, 'read_auth_json',
                        lambda *args, **kwargs: {'access_key': 'key', 'secret_key': 'secret'})
    monkeypatch.setattr(Provider, 'cmd_exec', mocked_cmd_exec)
    monkeypatch.setattr(EKS, 'aws_dir', lambda self: '/tmp')
    return EKS('fake')


def test_kubectl_client(eks_patch, monkeypatch):
    monkeypatch.setattr(EKS, "create_credentials_file", lambda self: None)
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(0))
    monkeypatch.setattr(kubernetes, 'config', MockedKubernetesConfig())
    mocked_client1 = MockedKubernetesClient(1)
    monkeypatch.setattr(kubernetes, 'client', mocked_client1)
    assert eks_patch.kubectl_client("region1", "cluster") == mocked_client1

    # Check that the client is reused
    mocked_client2 = MockedKubernetesClient(1)
    monkeypatch.setattr(kubernetes, 'client', mocked_client2)
    assert eks_patch.kubectl_client("region1", "cluster") == mocked_client1

    # Invalid 'aws eks update-kubeconfig' execution should return None
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(1))
    with pytest.raises(RuntimeError, match="Cannot get the kubeconfig for the cluster cluster on region region2"):
        eks_patch.kubectl_client("region2", "cluster")


def test_create_credentials_file(eks_patch, monkeypatch):
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(0))
    eks_patch.create_credentials_file()
    assert os.path.exists("/tmp/credentials")

    # Invalid credentials, 'aws sts get-caller-identity' fails
    monkeypatch.setattr(Provider, 'cmd_exec', lambda *args, **kwargs: MockedSubprocessReturn(returncode=1, stderr="test"))
    error = "Invalid credentials, the credentials cannot be verified by'aws sts get-caller-identity' with the error: test"
    with pytest.raises(RuntimeError, match=error):
        eks_patch.create_credentials_file()


def test_cleanup_k8s_jobs(eks_patch, monkeypatch):
    mocked_eks = MockedEKSClient()
    mocked_eks.clusters_list = {'clusters': ['cluster1']}
    monkeypatch.setattr(EKS, 'eks_client', lambda self, region: mocked_eks)

    monkeypatch.setattr(EKS, 'create_credentials_file', lambda *args, **kwargs: None)
    monkeypatch.setattr(kubernetes, 'config', MockedKubernetesConfig())
    mocked_kubernetes = MockedKubernetesClient([MockedKubernetesJob("job1", 1), MockedKubernetesJob("job2", 0)])
    monkeypatch.setattr(EKS, "kubectl_client", lambda *args, **kwargs: mocked_kubernetes)
    eks_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 1
    assert mocked_kubernetes.deleted_jobs[0] == "job1"

    # test dry_run
    eks_patch.dry_run = True
    mocked_kubernetes.deleted_jobs = []
    eks_patch.cleanup_k8s_jobs()
    assert len(mocked_kubernetes.deleted_jobs) == 0
