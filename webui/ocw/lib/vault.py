import requests
import base64
import json
from webui.settings import ConfigFile
from datetime import datetime
from datetime import timedelta


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
        if self.auth_json is None:
            self.auth_json = self.getCredentials()
            self.auth_expire = datetime.today() + timedelta(seconds=self.auth_json['lease_duration'])
        if name is None:
            return self.auth_json['data']
        return self.auth_json['data'][name]

    def isExpired(self):
        if self.auth_expire is None:
            return True
        return self.auth_expire < datetime.today()

    def renew(self):
        self.revoke()
        self.getData()


class AzureCredential(Vault):
    ''' Known data fields: subscription_id, client_id, client_secret, tenant_id
    '''

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        return super().__init__(url, user, password, certificate_dir)

    def getCredentials(self):

        path = '/v1/azure/creds/openqa-role'
        path_kv = '/v1/secret/azure/openqa-role'
        creds = self.httpGet(path).json()
        data = self.httpGet(path_kv).json()['data']
        for k, v in data.items():
            creds['data'][k] = v

        return creds


class EC2Credential(Vault):
    ''' Known data fields: access_key, secret_key '''

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        return super().__init__(url, user, password, certificate_dir)

    def getCredentials(self):
        path = '/v1/aws/creds/openqa-role'
        return self.httpGet(path).json()


class GCECredential(Vault):
    ''' Known data fields: private_key_data, project_id, private_key_id,
            private_key, client_email, client_id'''

    def __init__(self, url=None, user=None, password=None, certificate_dir=None):
        return super().__init__(url, user, password, certificate_dir)

    def getCredentials(self):
        path = '/v1/gcp/key/openqa-role'
        creds = self.httpGet(path).json()

        cred_file = json.loads(base64.b64decode(self.getData('private_key_data')))
        for k, v in cred_file.items():
            if k not in creds['data']:
                creds['data'][k] = v
        return creds
