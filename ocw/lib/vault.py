import requests
import base64
import json
from webui.settings import PCWConfig
from datetime import datetime
from datetime import timedelta
import dateutil.parser
from tempfile import NamedTemporaryFile
from pathlib import Path
import logging
import os
import inspect

logger = logging.getLogger(__name__)


class Vault:
    extra_time = 600

    def __init__(self, vault_namespace):
        self.url = PCWConfig.get_feature_property('vault', 'url')
        self.user = PCWConfig.get_feature_property('vault', 'user')
        self.namespace = vault_namespace
        self.password = PCWConfig.get_feature_property('vault', 'password')
        self.certificate_dir = PCWConfig.get_feature_property('vault', 'cert_dir')
        if PCWConfig.getBoolean('vault/use-file-cache') and self._getAuthCacheFile().exists():
            logger.info('Loading cached credentials')
            self.auth_json = self.loadAuthCache()
        else:
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
        except ConnectionError:
            logger.exception("Failed to revoke!")
        finally:
            self.auth_json = None
            self.client_token = None
            self.client_token_expire = None

    def getClientToken(self):
        if self.isClientTokenExpired():
            self.client_token = None
            self.client_token_expire = None
            j = self.httpPost('/v1/auth/userpass/login/' + self.user, data={'password': self.password})
            self.client_token = {'X-Vault-Token': j['auth']['client_token']}
            self.client_token_expire = datetime.today() + timedelta(seconds=j['auth']['lease_duration'])
        return self.client_token

    def isClientTokenExpired(self):
        if self.client_token is None:
            return True
        return self.client_token_expire < datetime.today() + timedelta(seconds=self.extra_time)

    def renewClientToken(self, increment):
        if self.isClientTokenExpired():
            return
        j = self.httpPost('/v1/auth/token/renew-self', headers=self.getClientToken(),
                          data={'increment': "{}s".format(increment)})
        self.client_token_expire = datetime.today() + timedelta(seconds=j['auth']['lease_duration'])
        if 'warnings' in j and j['warnings'] is not None:
            for w in j['warnings']:
                logger.warning("[{}][{}] {}".format(self.namespace, self.__class__.__name__, w))

    def __commonHttpRequestHandling(self, response):
        logger.debug("[{}] {} URL: {} || response status : {} || response : {}".format(
            self.namespace, inspect.stack()[1].function, response.url, response.status_code, response.text))
        response.raise_for_status()
        if 'json' not in response.headers['content-type']:
            raise ConnectionError('Unexpected response content-type: {}'.format(response.headers['content-type']))
        if len(response.content) > 0:
            json = response.json()
            if 'errors' in json:
                raise ConnectionError(",".join(json['errors']))
            return json
        else:
            return {}

    def httpGet(self, path):
        try:
            r = requests.get(self.url + path, headers=self.getClientToken(), verify=self.certificate_dir)
            return self.__commonHttpRequestHandling(r)
        except Exception as e:
            raise ConnectionError('{}: {}'.format(type(e).__name__, str(e)))

    def httpPost(self, path, data, headers={}):
        try:
            r = requests.post(self.url + path, json=data, headers=headers, verify=self.certificate_dir)
            return self.__commonHttpRequestHandling(r)
        except Exception as e:
            raise ConnectionError('{}: {}'.format(type(e).__name__, str(e)))

    def getCredentials(self):
        raise NotImplementedError

    def getData(self, name=None):
        use_file_cache = PCWConfig.getBoolean('vault/use-file-cache')
        if self.auth_json is None and use_file_cache:
            self.auth_json = self.loadAuthCache()
        if self.isExpired():
            self.auth_json = self.getCredentials()
            expire = datetime.today() + timedelta(seconds=self.auth_json['lease_duration'])
            self.auth_json['auth_expire'] = expire.isoformat()
            if expire > self.client_token_expire:
                self.renewClientToken(self.auth_json['lease_duration'])
            if use_file_cache:
                self.saveAuthCache()
        if name is None:
            return self.auth_json['data']
        return self.auth_json['data'][name]

    def getAuthExpire(self):
        if self.auth_json is None:
            return None
        return dateutil.parser.isoparse(self.auth_json['auth_expire'])

    def isExpired(self):
        expire = self.getAuthExpire()
        if expire is None:
            return True
        return expire < datetime.today() + timedelta(seconds=self.extra_time)

    def renew(self):
        if PCWConfig.getBoolean('vault/use-file-cache') and self._getAuthCacheFile().exists():
            self._getAuthCacheFile().unlink()
        self.revoke()
        self.getData()

    def _getAuthCacheFile(self):
        return Path('/tmp/pcw/{}/{}/auth.json'.format(self.__class__.__name__, self.namespace))

    def createAuthCachePath(self):
        oldmask = os.umask(0o077)
        path = self._getAuthCacheFile().parent
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        f = self._getAuthCacheFile()
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
        creds = self.httpGet(path)
        data = self.httpGet(path_kv)['data']
        for k, v in data.items():
            creds['data'][k] = v

        return creds


class EC2Credential(Vault):
    ''' Known data fields: access_key, secret_key '''

    def getCredentials(self):
        path = '/v1/{}/aws/creds/openqa-role'.format(self.namespace)
        return self.httpGet(path)


class GCECredential(Vault):
    ''' Known data fields: private_key_data, project_id, private_key_id,
            private_key, client_email, client_id'''
    cred_file = None

    def getCredentials(self):
        path = '/v1/{}/gcp/key/openqa-role'.format(self.namespace)
        creds = self.httpGet(path)
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
