import requests
import base64
import json
from webui.settings import ConfigFile
from datetime import datetime
from datetime import timedelta
from tempfile import NamedTemporaryFile


class Vault:
    client_token = None
    auth_json = None
    auth_expire = None

    def __init__(self):
        cfg = ConfigFile()
        self.url = cfg.get(['vault', 'url'])
        self.user = cfg.get(['vault', 'user'])
        self.password = cfg.get(['vault', 'password'])
        self.certificate_dir = cfg.get(['vault', 'cert_dir'], '/etc/ssl/certs')

    def __del__(self):
        self.revoke()

    def revoke(self):
        if self.auth_json is None:
            return
        try:
            self.httpPost('/v1/sys/leases/revoke', {'lease_id': self.auth_json['lease_id']}, self.getClientToken())
        except ConnectionError as e:
            # NoSuchEntity errors expected on revoke they just mean that Vault already did what we asking for
            if "NoSuchEntity:" not in str(e):
                raise e
        finally:
            self.auth_json = None

    def getClientToken(self):
        if self.client_token is None:
            r = self.httpPost('/v1/auth/userpass/login/' + self.user, data={'password': self.password})
            self.client_token = {'X-Vault-Token': r.json()['auth']['client_token']}
        return self.client_token

    def httpGet(self, path):
        try:
            r = requests.get(self.url + path, headers=self.getClientToken(), verify=self.certificate_dir)
            if len(r.content) > 0 and 'errors' in r.json():
                raise ConnectionError(",".join(r.json()['errors']))
            else:
                return r
        except Exception as e:
            raise ConnectionError('Connection failed - {}: {}'.format(type(e).__name__, str(e)))

    def httpPost(self, path, data, headers={}):
        try:
            r = requests.post(self.url + path, json=data, headers=headers, verify=self.certificate_dir)
            if len(r.content) > 0 and 'errors' in r.json():
                raise ConnectionError(",".join(r.json()['errors']))
            else:
                return r
        except Exception as e:
            raise ConnectionError('Connection failed - {}: {}'.format(type(e).__name__, str(e)))

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

    def getCredentials(self):
        path = '/v1/aws/creds/openqa-role'
        return self.httpGet(path).json()


class GCECredential(Vault):
    ''' Known data fields: private_key_data, project_id, private_key_id,
            private_key, client_email, client_id'''
    cred_file = None

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

    def getPrivateKeyData(self):
        return json.loads(base64.b64decode(self.getData('private_key_data')).decode(encoding='UTF-8'))

    def writetofile(self):
        if self.cred_file:
            self.cred_file.close()
            self.cred_file = None
        self.cred_file = NamedTemporaryFile()
        self.cred_file.write(base64.b64decode(self.getData('private_key_data')))
        self.cred_file.flush()
        return self.cred_file.name
