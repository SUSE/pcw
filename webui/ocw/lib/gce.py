from .vault import GCECredential
import googleapiclient.discovery
from google.oauth2 import service_account
from ..models import Instance
from ..models import ProviderChoice
from ..models import StateChoice
from django.db import transaction
from ..lib import db


class GCE:
    __instance = None
    __credentials = None
    __compute_clinet = None
    __project = None

    def __new__(cls):
        if GCE.__instance is None:
            GCE.__instance = object.__new__(cls)
            GCE.__instance.__credentials = GCECredential()
        return GCE.__instance

    def compute_client(self):
        if self.__credentials.isExpired():
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
        for region in GCE().list_regions():
            for zone in GCE().list_zones(region):
                result += GCE().list_instances(zone=zone)
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


def _instance_to_json(i):
    info = {
            'tags': {m['key']: m['value'] for m in i['metadata']['items']} if 'items' in i['metadata'] else {},
            'name': i['name'],
            'id': i['id'],
            'machineType': GCE.url_to_name(i['machineType']),
            'zone': GCE.url_to_name(i['zone']),
            'status': i['status'],
            'launch_time': i['creationTimestamp'],
            'creation_time': i['creationTimestamp'],
          }
    if 'openqa_created_date' in info['tags']:
        info['launch_time'] = info['tags']['openqa_created_date']
    info['tags'].pop('sshKeys', '')
    return info


@transaction.atomic
def sync_instances_db(instances):
    o = Instance.objects
    o = o.filter(provider=ProviderChoice.GCE)
    o = o.update(active=False)

    for i in instances:
        db.update_or_create_instance(
                provider=ProviderChoice.GCE,
                instance_id=i['id'],
                region=GCE.url_to_name(i['zone']),
                csp_info=_instance_to_json(i))

    o = Instance.objects
    o = o.filter(provider=ProviderChoice.GCE, active=False)
    o = o.update(state=StateChoice.DELETED)
