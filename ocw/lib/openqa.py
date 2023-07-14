from urllib.parse import urlparse
from cachetools import cached
import requests
from requests.exceptions import RequestException
from openqa_client.client import OpenQA_Client
from openqa_client.const import JOB_STATE_CANCELLED
from openqa_client.exceptions import OpenQAClientError


@cached(cache={})
def get_url(server):
    if server:
        server = server.rstrip('/').replace("_", ".")
    if urlparse(server).scheme != "":
        return server
    for scheme in ("https", "http"):
        try:
            url = f"{scheme}://{server}"
            got = requests.head(url, timeout=30)
            got.raise_for_status()
            return url
        except RequestException:
            pass
    raise OpenQAClientError(f"Could not connect to server {server}")


class OpenQA:
    __servers = {}

    def __new__(cls, **kwargs):
        server = urlparse(get_url(kwargs["server"])).netloc
        if server not in cls.__servers:
            cls.__servers[server] = self = super().__new__(cls)
            self.server = server
        return cls.__servers[server]

    def __init__(self, **kwargs):
        kwargs.pop("server")
        self.__client = OpenQA_Client(server=self.server, **kwargs)

    def is_cancelled(self, job_id: str) -> bool:
        if not job_id.isdigit():
            raise ValueError(f"job must be a number: {job_id}")
        try:
            status = self.__client.openqa_request('GET', f'jobs/{job_id}')
            # Return true if job is either cancelled or done
            return status['job']['state'] == JOB_STATE_CANCELLED
        except (TypeError, KeyError, OpenQAClientError):
            pass
        return False
