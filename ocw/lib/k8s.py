from datetime import datetime, timezone
from kubernetes.client import BatchV1Api, CoreV1Api
from ocw.lib.provider import Provider


def clean_jobs(provider: Provider, client: BatchV1Api, cluster_name: str):
    now = datetime.now(timezone.utc)
    ret = client.list_job_for_all_namespaces(watch=False)
    for job in ret.items:
        age = (now - job.status.start_time).days
        if age >= 1:
            if not provider.dry_run:
                provider.log_info(f"Deleting from {cluster_name} the job {job.metadata.name} " +
                                  f"with age {age} (days)")
                client.delete_namespaced_job(job.metadata.name, job.metadata.namespace)
            else:
                provider.log_info(f"Skip deleting from {cluster_name} the job {job.metadata.name} " +
                                  f"with age {age} (days)")


def clean_namespaces(provider: Provider, client: CoreV1Api, cluster_name: str):
    now = datetime.now(timezone.utc)
    # Retrieve the list of all namespaces
    namespaces = client.list_namespace(watch=False)

    for ns in namespaces.items:
        age = (now - ns.metadata.creation_timestamp).days
        if ns.metadata.name.startswith('helm-test') and age > 7:
            # Delete the namespace
            if provider.dry_run:
                provider.log_info(f"Skip deleting namespace {ns.metadata.name} created {ns.metadata.creation_timestamp}")
            else:
                provider.log_info(f"Deleting namespace {ns.metadata.name} created {ns.metadata.creation_timestamp}")
                client.delete_namespace(ns.metadata.name)
        else:
            provider.log_dbg(f"Namespace {ns.metadata.name} will be kept.")
