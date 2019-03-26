import requests
import base64
import json
from webui.settings import ConfigFile


class Vault:
    client_token = None
    auth_json = None

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
            self.certificate_dir = cfg.get(['vault', 'cert_dir'],
                                           '/etc/ssl/certs')

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
        if self.client_token is not None:
            return self.client_token

        r = requests.post(self.url+login_path+'/'+self.user,
                          json={'password': self.password},
                          verify=self.certificate_dir)
        self.client_token = r.json()['auth']['client_token']
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
        if name is None:
            return self.getCredentials()['data']
        return self.getCredentials()['data'][name]


class AzureCredential(Vault):
    ''' Known data fields: subscription_id, client_id, client_secret, tenant_id
    '''

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        return super().__init__(url, user, password, certificate_dir)

    def getCredentials(self):
        if self.auth_json is not None:
            return self.auth_json

        path = '/v1/azure/creds/openqa-role'
        path_kv = '/v1/secret/azure/openqa-role'
        creds = self.httpGet(path).json()
        data = self.httpGet(path_kv).json()['data']
        for k, v in data.items():
            creds['data'][k] = v

        self.auth_json = creds
        return self.auth_json


class EC2Credential(Vault):
    ''' Known data fields: access_key, secret_key '''

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        return super().__init__(url, user, password, certificate_dir)

    def getCredentials(self):
        if self.auth_json is not None:
            return self.auth_json

        path = '/v1/aws/creds/openqa-role'
        self.auth_json = self.httpGet(path).json()
        return self.auth_json


class GCECredential(Vault):
    ''' Known data fields: private_key_data, project_id, private_key_id,
            private_key, client_email, client_id'''

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        return super().__init__(url, user, password, certificate_dir)

    def getCredentials(self):
        if self.auth_json is not None:
            return self.auth_json

        path = '/v1/gcp/key/openqa-role'
        self.auth_json = self.httpGet(path).json()

        cred_file = json.loads(base64.b64decode(self.getData('private_key_data')))
        for k, v in cred_file.items():
            if k not in self.auth_json['data']:
                self.auth_json['data'][k] = v

        return self.auth_json
