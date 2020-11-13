from .vault import GCECredential
from .provider import Provider, Image
import googleapiclient.discovery
from google.oauth2 import service_account
from dateutil.parser import parse
import re



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
        if self.__credentials.isExpired():
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
        if self.dry_run:
            self.log_info("Deletion of instance {} skipped due to dry run mode", instance_id)
        else:
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
                    (-(?P<type>[-\w]+))?
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
        images = list()
        request = self.compute_client().images().list(project=self.__project)
        while request is not None:
            response = request.execute()
            if 'items' not in response:
                break
            for image in response['items']:
                # creation:2019-11-04T14:23:06.372-08:00
                # name:sles12-sp5-gce-x8664-0-9-1-byos-build1-56
                m = self.parse_image_name(image['name'])
                if m:
                    images.append(Image(image['name'], flavor=m['key'], build=m['build'],
                                        date=parse(image['creationTimestamp'])))
                    self.log_dbg('Image {} is candidate for deletion with build {}', image['name'], m['build'])
                else:
                    self.log_err("Unable to parse image name '{}'", image['name'])

            request = self.compute_client().images().list_next(previous_request=request, previous_response=response)

        keep_images = self.get_keeping_image_names(images)

        for img in [i for i in images if i.name not in keep_images]:
            self.log_info("Delete image '{}'", img.name)
            if self.dry_run:
                self.log_info("Deletion of image {} skipped due to dry run mode", img.name)
            else:
                request = self.compute_client().images().delete(project=self.__project, image=img.name)
                response = request.execute()
                if 'error' in response:
                    for e in response['error']['errors']:
                        self.log_err(e['message'])
                if 'warnings' in response:
                    for w in response['warnings']:
                        self.log_warn(w['message'])
