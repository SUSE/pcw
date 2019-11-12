import requests
import base64
import json
from webui.settings import ConfigFile
from datetime import datetime
from datetime import timedelta
import dateutil.parser
from tempfile import NamedTemporaryFile
from pathlib import Path
import logging
import os

logger = logging.getLogger(__name__)


class Vault:
    extra_time = 600

    def __init__(self, vault_namespace):
        cfg = ConfigFile()
        self.url = cfg.get(['vault', 'url'])
        self.user = cfg.get(['vault', 'user'])
        self.namespace = vault_namespace
        self.password = cfg.get(['vault', 'password'])
        self.certificate_dir = cfg.get(['vault', 'cert_dir'], '/etc/ssl/certs')
        self.auth_json = None
        self.client_token = None
        self.client_token_expire = None

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
        if self.isClientTokenExpired():
            r = self.httpPost('/v1/auth/userpass/login/' + self.user, data={'password': self.password})
            j = r.json()
            self.client_token = {'X-Vault-Token': j['auth']['client_token']}
            self.client_token_expire = datetime.today() + timedelta(seconds=j['auth']['lease_duration'])
        return self.client_token

    def isClientTokenExpired(self):
        if self.client_token is None:
            return True
        return self.client_token_expire < datetime.today() + timedelta(seconds=self.extra_time)

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
        use_file_cache = ConfigFile().getBoolean(['vault', 'use-file-cache'])
        if self.auth_json is None and use_file_cache:
            self.auth_json = self.loadAuthCache()
        if self.isValid():
            self.auth_json = self.getCredentials()
            expire = datetime.today() + timedelta(seconds=self.auth_json['lease_duration'])
            self.auth_json['auth_expire'] = expire.isoformat()
            if use_file_cache:
                self.saveAuthCache()
        if name is None:
            return self.auth_json['data']
        return self.auth_json['data'][name]

    def getAuthExpire(self):
        if self.auth_json is None:
            return None
        return dateutil.parser.isoparse(self.auth_json['auth_expire'])

    def isValid(self):
        if self.auth_json is None:
            return True
        expire = dateutil.parser.isoparse(self.auth_json['auth_expire'])
        return expire < datetime.today() + timedelta(seconds=self.extra_time)

    def renew(self):
        self.revoke()
        self.getData()

    def createAuthCachePath(self):
        oldmask = os.umask(0o077)
        path = Path('/tmp/pcw/{}/{}'.format(self.__class__.__name__, self.namespace))
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        f = path.joinpath('auth.json')
        f.touch(mode=0o600, exist_ok=True)
        os.umask(oldmask)
        return f

    def loadAuthCache(self):
        try:
            authcachepath = self.createAuthCachePath()
            if authcachepath.stat().st_size == 0:
                return None
            with authcachepath.open() as f:
                logger.info("Try loading auth cache from file {}".format(f.name))
                return json.loads(f.read())
        except json.decoder.JSONDecodeError:
            logger.warning("Failed to load auth cache file")
        except Exception:
            logger.exception("Failed to load auth cache")
        return None

    def saveAuthCache(self):
        try:
            with self.createAuthCachePath().open('w') as f:
                logger.info("Write auth cache to file {}".format(f.name))
                f.write(json.dumps(self.auth_json))
        except Exception:
            logger.exception("Failed to save auth cache")


class AzureCredential(Vault):
    ''' Known data fields: subscription_id, client_id, client_secret, tenant_id
    '''

    def getCredentials(self):

        path = '/v1/{}/azure/creds/openqa-role'.format(self.namespace)
        path_kv = '/v1/{}/secret/azure/openqa-role'.format(self.namespace)
        creds = self.httpGet(path).json()
        data = self.httpGet(path_kv).json()['data']
        for k, v in data.items():
            creds['data'][k] = v

        return creds


class EC2Credential(Vault):
    ''' Known data fields: access_key, secret_key '''

    def getCredentials(self):
        path = '/v1/{}/aws/creds/openqa-role'.format(self.namespace)
        return self.httpGet(path).json()


class GCECredential(Vault):
    ''' Known data fields: private_key_data, project_id, private_key_id,
            private_key, client_email, client_id'''
    cred_file = None

    def getCredentials(self):
        path = '/v1/{}/gcp/key/openqa-role'.format(self.namespace)
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
