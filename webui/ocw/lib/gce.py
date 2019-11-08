from .vault import GCECredential
import googleapiclient.discovery
from google.oauth2 import service_account


class GCE:
    __instances = dict()
    __credentials = None
    __compute_clinet = None
    __project = None

    def __new__(cls, vault_namespace):
        if vault_namespace not in GCE.__instances:
            GCE.__instances[vault_namespace] = object.__new__(cls)
            GCE.__instances[vault_namespace].__credentials = GCECredential(vault_namespace)
        return GCE.__instances[vault_namespace]

    def compute_client(self):
        if self.__credentials.isValid():
            self.__credentials.renew()
            self.__compute_clinet = None
        self.__project = self.__credentials.getPrivateKeyData()['project_id']
        if(self.__compute_clinet is None):
            credentials = service_account.Credentials.from_service_account_info(self.__credentials.getPrivateKeyData())
            self.__compute_clinet = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)
        return self.__compute_clinet

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
