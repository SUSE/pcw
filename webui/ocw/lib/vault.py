import requests
import base64
import json
import time
import boto3
import googleapiclient.discovery
from google.oauth2 import service_account
from webui.settings import ConfigFile
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from datetime import datetime
from datetime import timedelta
from tempfile import NamedTemporaryFile
from msrest.exceptions import AuthenticationError


class Vault:
    client_token = None
    auth_json = None
    auth_expire = None

    def __init__(self, url, user, password, certificate_dir):
        self.url = url
        self.user = user
        self.password = password
        self.certificate_dir = certificate_dir
        cfg = ConfigFile()
        if (self.url is None):
            self.url = cfg.get(['vault', 'url'])
            self.user = cfg.get(['vault', 'user'])
            self.password = cfg.get(['vault', 'password'])
            self.certificate_dir = cfg.get(['vault', 'cert_dir'], '/etc/ssl/certs')

    def __del__(self):
        self.revoke()

    def revoke(self):
        if self.auth_json is None:
            return
        path = '/v1/sys/leases/revoke'
        self.httpPost(path, {'lease_id': self.auth_json['lease_id']})
        self.auth_json = None

    def getClientToken(self):
        login_path = '/v1/auth/userpass/login'
        if self.client_token is None:
            try:
                r = requests.post(self.url+login_path+'/'+self.user,
                                  json={'password': self.password},
                                  verify=self.certificate_dir)
                if 'errors' in r.json():
                    raise ConnectionError(",".join(r.json()['errors']))
                self.client_token = r.json()['auth']['client_token']
            except Exception as e:
                raise ConnectionError('Vault login failed - {}: {}'.format(type(e).__name__, str(e)))

        return self.client_token

    def httpGet(self, path):
        return requests.get(self.url + path,
                            headers={'X-Vault-Token': self.getClientToken()},
                            verify=self.certificate_dir)

    def httpPost(self, path, data):
        return requests.post(self.url + path,
                             json=data,
                             headers={'X-Vault-Token': self.getClientToken()},
                             verify=self.certificate_dir)

    def getCredentials(self):
        raise NotImplementedError

    def getData(self, name=None):
        if self.isExpired():
            self.revoke()
        if self.auth_json is None:
            self.auth_json = self.getCredentials()
            self.auth_expire = datetime.today() + timedelta(seconds=self.auth_json['lease_duration'])
        if name is None:
            return self.auth_json['data']
        return self.auth_json['data'][name]

    def isExpired(self):
        return self.auth_expire is None or self.auth_expire < datetime.today()


class AzureCredential(Vault):
    ''' Known data fields: subscription_id, client_id, client_secret, tenant_id
    '''

    __compute_mgmt_client = None
    __sp_credentials = None
    __resource_mgmt_client = None

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        super().__init__(url, user, password, certificate_dir)
        for i in range(1, 40):
            try:
                self.sp_credentials()
                return True
            except AuthenticationError as e:
                print('ServicePrincipalCredentials failed (attemp:{}) - {}'.format(i, str(e)))
                time.sleep(1)
        raise AuthenticationError("Invalid Azure credentials")

    def getCredentials(self):

        path = '/v1/azure/creds/openqa-role'
        path_kv = '/v1/secret/azure/openqa-role'
        creds = self.httpGet(path).json()
        data = self.httpGet(path_kv).json()['data']
        for k, v in data.items():
            creds['data'][k] = v

        return creds

    def sp_credentials(self):
        if (self.__sp_credentials is None or self.isExpired()):
            self.__sp_credentials = ServicePrincipalCredentials(client_id=self.getData('client_id'),
                                                                secret=self.getData('client_secret'),
                                                                tenant=self.getData('tenant_id')
                                                                )
        return self.__sp_credentials

    def compute_mgmt_client(self):
        if (self.__compute_mgmt_client is None or self.isExpired()):
            self.__compute_mgmt_client = ComputeManagementClient(
                self.sp_credentials(), self.getData('subscription_id'))
        return self.__compute_mgmt_client

    def resource_mgmt_client(self):
        if (self.__resource_mgmt_client is None or self.isExpired()):
            self.__resoure_mgmt_client = ResourceManagementClient(
                self.sp_credentials(), self.getData('subscription_id'))
        return self.__resoure_mgmt_client


class EC2Credential(Vault):
    ''' Known data fields: access_key, secret_key '''

    __key = None
    __secret = None
    __ec2_resource = dict()
    __ec2_client = dict()

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        super().__init__(url, user, password, certificate_dir)

        self.__secret = self.getData('secret_key')
        self.__key = self.getData('access_key')

        for i in range(1, 60 * 5):
            try:
                self.list_regions()
                return True
            except Exception as e:
                print('CredentialsError (attemp:{}) - {}'.format(i, str(e)))
                time.sleep(1)
        raise Exception("Invalid EC2 credentials")

    def list_regions(self):
        regions_resp = self.ec2_client().describe_regions()
        regions = [region['RegionName'] for region in regions_resp['Regions']]
        return regions

    def getCredentials(self):
        path = '/v1/aws/creds/openqa-role'
        return self.httpGet(path).json()

    def ec2_resource(self, region='eu-central-1'):
        if region not in self.__ec2_resource:
            self.__ec2_resource[region] = boto3.resource('ec2', aws_access_key_id=self.__key,
                                                         aws_secret_access_key=self.__secret,
                                                         region_name=region)
        return self.__ec2_resource[region]

    def ec2_client(self, region='eu-central-1'):
        if region not in self.__ec2_client:
            self.__ec2_client[region] = boto3.client('ec2', aws_access_key_id=self.__key,
                                                     aws_secret_access_key=self.__secret,
                                                     region_name=region)
        return self.__ec2_client[region]


class GCECredential(Vault):
    ''' Known data fields: private_key_data, project_id, private_key_id,
            private_key, client_email, client_id'''
    __cred_file = None
    __compute_clinet = None

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        self.__cred_file = None
        return super().__init__(url, user, password, certificate_dir)

    def getCredentials(self):
        path = '/v1/gcp/key/openqa-role'
        creds = self.httpGet(path).json()
        if 'errors' in creds:
            raise Exception(",".join(creds['errors']))
        cred_file = json.loads(base64.b64decode(creds['data']['private_key_data']).decode(encoding='UTF-8'))
        for k, v in cred_file.items():
            if k not in creds['data']:
                creds['data'][k] = v
        return creds

    def compute_client(self):
        if(self.__compute_clinet is None or self.isExpired()):
            credentials = service_account.Credentials.from_service_account_info(self.getPrivateKeyData())
            self.__compute_clinet = googleapiclient.discovery.build('compute', 'v1', credentials=credentials)
        return self.__compute_clinet

    def list_instances(self, zone='europe-west1-b'):
        i = self.compute_client().instances().list(project=self.getPrivateKeyData()['project_id'], zone=zone).execute()
        return i['items'] if 'items' in i else []

    def getPrivateKeyData(self):
        return json.loads(base64.b64decode(self.getData('private_key_data')).decode(encoding='UTF-8'))

    def writetofile(self):
        if self.__cred_file:
            self.__cred_file.close()
            self.__cred_file = None
        self.__cred_file = NamedTemporaryFile()
        self.__cred_file.write(base64.b64decode(self.getData('private_key_data')))
        self.__cred_file.flush()
        return self.__cred_file.name
