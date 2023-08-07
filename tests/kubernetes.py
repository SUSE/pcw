from datetime import datetime, timezone, timedelta


class MockedKubernetesConfig():
    def load_kube_config(self, *args, **kwargs):
        return True


class MockedKubernetesClient():
    def __init__(self, jobs=None, namespaces=None):
        if jobs is None:
            jobs = []
        if namespaces is None:
            namespaces = []
        self.jobs = jobs
        self.namespaces = namespaces
        self.deleted_jobs = []
        self.deleted_namespaces = []

    # pylint: disable=C0103
    def BatchV1Api(self):
        return self

    # pylint: disable=C0103
    def CoreV1Api(self):
        return self

    def list_job_for_all_namespaces(self, *args, **kwargs):
        return MockedKubernetesResult(self.jobs)

    def delete_namespaced_job(self, name, namespace):
        self.deleted_jobs.append(name)

    def list_namespace(self, *args, **kwargs):
        return MockedKubernetesResult(self.namespaces)

    def delete_namespace(self, name):
        self.deleted_namespaces.append(name)


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


class MockedKubernetesNamespaceMetadata():
    def __init__(self, name, age):
        self.name = name
        self.creation_timestamp = datetime.now(timezone.utc) - timedelta(days=age)


class MockedKubernetesNamespace():
    def __init__(self, name, age):
        self.metadata = MockedKubernetesNamespaceMetadata(name, age)


class MockedSubprocessReturn():
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = stdout
