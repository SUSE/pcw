from .vault import GCECredential
from .provider import Provider
import googleapiclient.discovery
from google.oauth2 import service_account
from dateutil.parser import parse
import re
import logging
from distutils.version import LooseVersion

logger = logging.getLogger(__name__)


class GCE(Provider):
    __instances = dict()

    def __new__(cls, vault_namespace):
        if vault_namespace not in GCE.__instances:
            GCE.__instances[vault_namespace] = self = object.__new__(cls)
            self.__credentials = GCECredential(vault_namespace)
            self.__compute_client = None
            self.__project = None
        return GCE.__instances[vault_namespace]

    def compute_client(self):
        if self.__credentials.isValid():
            self.__credentials.renew()
            self.__compute_client = None
        self.__project = self.__credentials.getPrivateKeyData()['project_id']
        if(self.__compute_client is None):
            credentials = service_account.Credentials.from_service_account_info(self.__credentials.getPrivateKeyData())
            self.__compute_client = googleapiclient.discovery.build('compute', 'v1', credentials=credentials,
                                                                    cache_discovery=False)
        return self.__compute_client

    def list_instances(self, zone):
        ''' List all instances by zone.'''
        result = []
        request = self.compute_client().instances().list(project=self.__project, zone=zone)
        while request is not None:
            response = request.execute()
            if 'items' in response:
                result += response['items']
            request = self.compute_client().instances().list_next(previous_request=request, previous_response=response)
        return result

    def list_all_instances(self):
        result = []
        for region in self.list_regions():
            for zone in self.list_zones(region):
                result += self.list_instances(zone=zone)
        return result

    def list_regions(self):
        '''Walk through all regions->zones and collect all instances to return them as list.
           @see https://cloud.google.com/compute/docs/reference/rest/v1/instances/list#examples'''
        result = []
        request = self.compute_client().regions().list(project=self.__project)
        while request is not None:
            response = request.execute()

            for region in response['items']:
                result.append(region['name'])
            request = self.compute_client().regions().list_next(previous_request=request, previous_response=response)
        return result

    def list_zones(self, region):
        region = self.compute_client().regions().get(project=self.__project, region=region).execute()
        return [GCE.url_to_name(z) for z in region['zones']]

    def delete_instance(self, instance_id, zone):
        self.compute_client().instances().delete(project=self.__project, zone=zone, instance=instance_id).execute()

    @staticmethod
    def url_to_name(url):
        return url[url.rindex('/')+1:]

    def parse_image_name(self, img_name):
        regexes = [
            # sles12-sp5-gce-x8664-0-9-1-byos-build1-56
            re.compile(r'''^sles
                    (?P<version>\d+(-sp\d+)?)
                    -
                    (?P<flavor>gce)
                    -
                    (?P<arch>[^-]+)
                    -
                    (?P<kiwi>\d+-\d+-\d+)
                    -
                    (?P<type>(byos|on-demand))
                    -build
                    (?P<build>\d+-\d+)
                    ''', re.RegexFlag.X),
            # sles15-sp2-byos-x8664-0-9-3-gce-build1-10
            # sles15-sp2-x8664-0-9-3-gce-build1-10
            re.compile(r'''^sles
                    (?P<version>\d+(-sp\d+)?)
                    (-(?P<type>\w+))?
                    -
                    (?P<arch>[^-]+)
                    -
                    (?P<kiwi>\d+-\d+-\d+)
                    -
                    (?P<flavor>gce)
                    -
                    build
                    (?P<build>\d+-\d+)
                    ''', re.RegexFlag.X)
        ]
        return self.parse_image_name_helper(img_name, regexes)

    def cleanup_all(self):
        images = dict()
        request = self.compute_client().images().list(project=self.__project)
        while request is not None:
            response = request.execute()
            if 'items' not in response:
                break
            for image in response['items']:
                logger.debug('Found image {}'.format(image['name']))
                # creation:2019-11-04T14:23:06.372-08:00
                # name:sles12-sp5-gce-x8664-0-9-1-byos-build1-56
                m = self.parse_image_name(image['name'])
                if m:
                    key = m['key']
                    if key not in images:
                        images[key] = list()

                    images[key].append({
                        'build': m['build'],
                        'name': image['name'],
                        'creation_datetime':  parse(image['creationTimestamp']),
                    })
                else:
                    logger.error("[GCE][{}] Unable to parse image name '{}'".format(
                        self.__credentials.namespace, image['name']))

            request = self.compute_client().images().list_next(previous_request=request, previous_response=response)

        for key in images:
            images[key].sort(key=lambda x: LooseVersion(x['build']))

        for img_list in images.values():
            for i in range(0, len(img_list)):
                img = img_list[i]
                if (self.needs_to_delete_image(i, img['creation_datetime'])):
                    logger.info("[GCE] Delete image '{}'".format(img['name']))
                    request = self.compute_client().images().delete(project=self.__project, image=img['name'])
                    response = request.execute()
                    if 'error' in response:
                        for e in response['error']['errors']:
                            logger.error(e['message'])
                    if 'warnings' in response:
                        for w in response['warnings']:
                            logger.error(w['message'])
