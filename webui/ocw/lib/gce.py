from .vault import GCECredential
from .provider import Provider
import googleapiclient.discovery
from google.oauth2 import service_account
from dateutil.parser import parse
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import logging
from distutils.version import LooseVersion

logger = logging.getLogger(__name__)


class GCE(Provider):
    __instances = dict()
    __credentials = None
    __compute_client = None
    __project = None

    def __new__(cls, vault_namespace):
        if vault_namespace not in GCE.__instances:
            GCE.__instances[vault_namespace] = object.__new__(cls)
            GCE.__instances[vault_namespace].__credentials = GCECredential(vault_namespace)
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

    def cleanup_all(self):
        images = dict()
        request = self.compute_client().images().list(project=self.__project)
        while request is not None:
            response = request.execute()
            for image in response['items']:
                logger.debug('Found image {}'.format(image['name']))
                # creation:2019-11-04T14:23:06.372-08:00
                # name:sles12-sp5-gce-x8664-0-9-1-byos-build1-56
                regex = re.compile(r'''^sles
                            (?P<version>\d+(-sp\d+)?)
                            -gce-
                            (?P<arch>[^-]+)
                            -
                            (?P<kiwi>\d+-\d+-\d+)
                            -
                            (?P<flavor>(byos|on-demand))
                            -build
                            (?P<build>\d+-\d+)
                            ''', re.RegexFlag.X)
                m = re.match(regex, image['name'])
                if m:
                    key = '-'.join([m.group('version'), m.group('flavor'), m.group('arch')])
                    if key not in images:
                        images[key] = list()

                    images[key].append({
                        'build': "-".join([m.group('kiwi'), m.group('build')]),
                        'name': image['name'],
                        'creation_datetime':  parse(image['creationTimestamp']),
                        })
                else:
                    logger.error("Unable to parse image name '{}'".format(image['name']))

            request = self.compute_client().images().list_next(previous_request=request, previous_response=response)

        for key in images:
            images[key].sort(key=lambda x: LooseVersion(x['build']))

        max_images_per_flavor = self.cfgGet('cleanup', 'max-images-per-flavor')
        max_images_age_hours = self.cfgGet('cleanup', 'max-images-age-hours')
        dead_line = datetime.now(timezone.utc) - timedelta(hours=max_images_age_hours)
        for img_list in images.values():
            for i in range(0, len(img_list)):
                img = img_list[i]
                if i < len(img_list) - max_images_per_flavor or img['creation_datetime'] < dead_line:
                    logger.info("[GCE] Delete image '{}'".format(img['name']))
                    request = self.compute_client().images().delete(project=self.__project, image=img['name'])
                    response = request.execute()
                    if 'error' in response:
                        for e in response['error']['errors']:
                            logger.error(e['message'])
                    if 'warnings' in response:
                        for w in response['warnings']:
                            logger.error(w['message'])
