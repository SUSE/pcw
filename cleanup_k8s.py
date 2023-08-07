import os
import logging
from ocw.lib.gke import GKE
from ocw.lib.eks import EKS
from ocw.lib.aks import AKS
from ocw.enums import ProviderChoice
from webui.PCWConfig import PCWConfig, ConfigFile, CONFIG_FILE


def main():
    loglevel = 'INFO'
    if os.path.exists(CONFIG_FILE):
        loglevel = ConfigFile().get('default/loglevel', loglevel)

    logger = logging.getLogger(__name__)
    logging.basicConfig(level=loglevel)

    for namespace in PCWConfig.get_namespaces_for('k8sclusters'):
        providers = PCWConfig.get_providers_for("k8sclusters", namespace)
        try:
            if ProviderChoice.GCE in providers:
                GKE(namespace).cleanup_k8s_jobs()
                GKE(namespace).cleanup_k8s_namespaces()
            if ProviderChoice.EC2 in providers:
                EKS(namespace).cleanup_k8s_jobs()
                EKS(namespace).cleanup_k8s_namespaces()
            if ProviderChoice.AZURE in providers:
                AKS(namespace).cleanup_k8s_jobs()
                AKS(namespace).cleanup_k8s_namespaces()
        except Exception:
            logger.exception("[%s] Cleanup failed!", namespace)


if __name__ == "__main__":
    main()
