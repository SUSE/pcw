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

    def write(self, measurement: str, field: str, value: int) -> None:
        if self.__client:
            point = Point(measurement).field(field, value)
            try:
                self.__client.write(bucket=self.bucket, org=self.org, record=point)
            except (InfluxDBError, HTTPError) as exception:
                logger.warning("Failed to write to influxdb(record=%s): %s", point, exception)

    def dump_resource(self, provider: str, field: str, dump_method: Callable) -> None:
        items_cnt = len(dump_method())
        logger.debug("%d instances found in %s", items_cnt, provider)
        self.write(provider, field, items_cnt)
