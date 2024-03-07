import logging
import traceback
from webui.PCWConfig import PCWConfig
from ocw.lib.azure import Azure
from ocw.enums import ProviderChoice
from ocw.lib.influx import Influx

logger = logging.getLogger(__name__)


def dump_state():
    for namespace in PCWConfig.get_namespaces_for('influxdb'):
        try:
            providers = PCWConfig.get_providers_for('influxdb', namespace)
            logger.info("[%s] Dump state %s", namespace, ','.join(providers))
            if ProviderChoice.AZURE in providers:
                Influx().dump_resource(ProviderChoice.AZURE.value, Influx.VMS_QUANTITY, Azure(namespace).list_instances)
                Influx().dump_resource(ProviderChoice.AZURE.value, Influx.IMAGES_QUANTITY, Azure(namespace).list_images)
                Influx().dump_resource(ProviderChoice.AZURE.value, Influx.DISK_QUANTITY, Azure(namespace).list_disks)
                Influx().dump_resource(ProviderChoice.AZURE.value, Influx.IMAGE_VERSION_QUANTITY, Azure(namespace).get_img_versions_count)
        except Exception:
            logger.exception("[%s] Dump state failed!: \n %s", namespace, traceback.format_exc())
