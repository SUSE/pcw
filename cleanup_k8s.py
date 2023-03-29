import logging
from ocw.lib.gke import GKE
from ocw.lib.eks import EKS
from ocw.lib.aks import AKS
from ocw.enums import ProviderChoice
from webui.PCWConfig import PCWConfig


def main():
    logger = logging.getLogger(__name__)

    for namespace in PCWConfig.get_namespaces_for('k8sclusters'):
        providers = PCWConfig.get_providers_for("k8sclusters", namespace)
        try:
            if ProviderChoice.GCE in providers:
                GKE(namespace).cleanup_k8s_jobs()
            if ProviderChoice.EC2 in providers:
                EKS(namespace).cleanup_k8s_jobs()
            if ProviderChoice.AZURE in providers:
                AKS(namespace).cleanup_k8s_jobs()
        except Exception:
            logger.exception("[%s] Cleanup failed!", namespace)


if __name__ == "__main__":
    main()
