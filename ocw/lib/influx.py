from typing import Callable
import os
import logging
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WriteApi
from influxdb_client.client.exceptions import InfluxDBError
from urllib3.exceptions import HTTPError


from webui.PCWConfig import PCWConfig

logger = logging.getLogger(__name__)


class Influx:
    __client: WriteApi | None = None
    VMS_QUANTITY: str = "vms_quantity"
    IMAGES_QUANTITY: str = "images_quantity"
    DISK_QUANTITY: str = "disk_quantity"
    VOLUMES_QUANTITY: str = "volumes_quanity"
    IMAGE_VERSION_QUANTITY: str = "img_version_quantity"
    VPC_QUANTITY: str = "vpc_quantity"
    NAMESPACE_TAG: str = "namespace"

    def __init__(self) -> None:
        if self.__client is None:
            if os.getenv("INFLUX_TOKEN") is None:
                logger.warning("INFLUX_TOKEN is not set, InfluxDB will not be used")
            elif PCWConfig.has("influxdb/url"):
                self.bucket: str = str(PCWConfig.get_feature_property("influxdb", "bucket"))
                self.org: str = str(PCWConfig.get_feature_property("influxdb", "org"))
                url: str = str(PCWConfig.get_feature_property("influxdb", "url"))
                self.__client = InfluxDBClient(
                    url=url,
                    token=os.getenv("INFLUX_TOKEN"),
                    org=str(PCWConfig.get_feature_property("influxdb", "org")),
                ).write_api(write_options=SYNCHRONOUS)

    # this is implementation of Singleton pattern
    def __new__(cls: type["Influx"]) -> "Influx":
        if not hasattr(cls, "instance") or cls.instance is None:
            cls.instance = super(Influx, cls).__new__(cls)
        return cls.instance

    def write(self, measurement: str, field: str, value: int, namespace: str) -> None:
        if self.__client:
            point = Point(measurement).field(field, value).tag(Influx.NAMESPACE_TAG, namespace)
            try:
                self.__client.write(bucket=self.bucket, org=self.org, record=point)
            except (InfluxDBError, HTTPError) as exception:
                logger.warning("Failed to write to influxdb(record=%s): %s", point, exception)

    def dump_resource(self, provider: str, field: str, namespace: str, dump_method: Callable) -> None:
        return_value = dump_method()
        if isinstance(return_value, list):
            items_cnt = len(return_value)
        elif isinstance(return_value, int):
            items_cnt = return_value
        else:
            raise ValueError(f"{dump_method} returned unsupported type {type(return_value)}")
        logger.debug("%s=%d for %s", field, items_cnt, provider)
        self.write(provider, field, items_cnt, namespace=namespace)
