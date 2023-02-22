import logging
from ocw.lib.gke import GKE
from webui.settings import PCWConfig
from ocw.enums import ProviderChoice


def main():
    logger = logging.getLogger(__name__)

    for namespace in PCWConfig.get_namespaces_for('cleanup'):
        providers = PCWConfig.get_providers_for('cleanup', namespace)
        try:
            if ProviderChoice.GCE in providers:
                GKE(namespace).cleanup_k8s_jobs()
        except Exception:
            logger.exception("[%s] Cleanup failed!", namespace)


if __name__ == "__main__":
    main()
