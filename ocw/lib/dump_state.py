import os
import logging
import traceback
from webui.PCWConfig import PCWConfig
from ocw.lib.azure import Azure
from ocw.lib.ec2 import EC2
from ocw.lib.gce import GCE
from ocw.enums import ProviderChoice
from ocw.lib.influx import Influx

logger = logging.getLogger(__name__)


def dump_state():
    if os.getenv("INFLUX_TOKEN") is None:
        logger.warning("INFLUX_TOKEN is not set, dumping state is not possible")
        return
    if not PCWConfig.has("influxdb/url"):
        logger.warning("pcw.ini missing influxdb configuration, dumping state is not possible")
        return
    for namespace in PCWConfig.get_namespaces_for("influxdb"):
        try:
            providers = PCWConfig.get_providers_for("influxdb", namespace)
            logger.info("[%s] Dump state %s", namespace, ",".join(providers))
            if ProviderChoice.AZURE in providers:
                Influx().dump_resource(
                    ProviderChoice.AZURE.value,
                    Influx.VMS_QUANTITY,
                    namespace,
                    Azure(namespace).list_instances,
                )
                Influx().dump_resource(
                    ProviderChoice.AZURE.value,
                    Influx.IMAGES_QUANTITY,
                    namespace,
                    Azure(namespace).list_images,
                )
                Influx().dump_resource(
                    ProviderChoice.AZURE.value,
                    Influx.DISK_QUANTITY,
                    namespace,
                    Azure(namespace).report_list_disks,
                )
                Influx().dump_resource(
                    ProviderChoice.AZURE.value,
                    Influx.IMAGE_VERSION_QUANTITY,
                    namespace,
                    Azure(namespace).get_img_versions_count,
                )
            if ProviderChoice.EC2 in providers:
                Influx().dump_resource(
                    ProviderChoice.EC2.value,
                    Influx.VMS_QUANTITY,
                    namespace,
                    EC2(namespace).count_all_instances
                )
                Influx().dump_resource(
                    ProviderChoice.EC2.value,
                    Influx.IMAGES_QUANTITY,
                    namespace,
                    EC2(namespace).count_all_images
                )
                Influx().dump_resource(
                    ProviderChoice.EC2.value,
                    Influx.VOLUMES_QUANTITY,
                    namespace,
                    EC2(namespace).count_all_volumes
                )
                Influx().dump_resource(
                    ProviderChoice.EC2.value,
                    Influx.VPC_QUANTITY,
                    namespace,
                    EC2(namespace).count_all_vpc
                )
            if ProviderChoice.GCE in providers:
                Influx().dump_resource(
                    ProviderChoice.GCE.value,
                    Influx.VMS_QUANTITY,
                    namespace,
                    GCE(namespace).count_all_instances
                )
                Influx().dump_resource(
                    ProviderChoice.GCE.value,
                    Influx.IMAGES_QUANTITY,
                    namespace,
                    GCE(namespace).count_all_images
                )
                Influx().dump_resource(
                    ProviderChoice.GCE.value,
                    Influx.DISK_QUANTITY,
                    namespace,
                    GCE(namespace).count_all_disks
                )
                Influx().dump_resource(
                    ProviderChoice.GCE.value,
                    Influx.BLOB_QUANTITY,
                    namespace,
                    GCE(namespace).count_all_blobs
                )
                Influx().dump_resource(
                    ProviderChoice.GCE.value,
                    Influx.NETWORK_QUANTITY,
                    namespace,
                    GCE(namespace).count_all_networks
                )
        except Exception:
            logger.exception(
                "[%s] Dump state failed!: \n %s", namespace, traceback.format_exc()
            )
