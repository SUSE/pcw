from ocw.lib.vault import Vault, AzureCredential, EC2Credential, GCECredential
from datetime import datetime
from datetime import timedelta
import pytest
import requests
import webui
import json
import base64
from pathlib import Path, PurePath
from faker import Faker


# Global test data
namespace = 'test-qa'
host = 'http://foo.bar'
leases = list()
tokens = list()
working_dir = Path(PurePath(Path(__file__).absolute()).parent)
authfile = Path(working_dir / 'auth.json')
fake = Faker()


class MockResponse:
    def __init__(self, json_response={}, status_code=200):
        self.json_response = json_response
        self.content = json.dumps(json_response)
        self.status_code = status_code

    def json(self):
        return self.json_response


def mock_post(url, **kwargs):
    global leases
    if (url.startswith('{}/v1/auth/userpass/login/'.format(host))):
        username = url[38:]
        password = kwargs['json']['password']
        if (username == 'devel' and password == 'sag_ich_nicht'):
            client_token = fake.uuid4()
            tokens.append(client_token)
            return MockResponse({'auth': {'client_token': client_token, 'lease_duration': 60*15}})
        return MockResponse({'errors': ['Unknown user']}, status_code=401)

    assert kwargs['headers']['X-Vault-Token'] == tokens[-1]

    if (url.startswith('{}/v1/sys/leases/revoke'.format(host))):
        lease_id = kwargs['json']['lease_id']
        if (lease_id in leases):
            leases.remove(lease_id)
            return MockResponse(status_code=200)
        else:
            return MockResponse({'errors': ['Some other Error', 'NoSuchEntity:', 'Error msg 2']}, 404)

    if (url == '{}/v1/auth/token/renew-self'.format(host)):
        increment = kwargs['json']['increment']
        response = {'auth': {'client_token': kwargs['headers']['X-Vault-Token'], 'lease_duration': 666}}

        if increment == "{}s".format(60 * 60 * 55):
            response['warnings'] = None
            return MockResponse(response)

        if increment == "{}s".format(60 * 60 * 666):
            response['warnings'] = ["TTL of \"666h0m0s\" exceeded the effective max_ttl of \"5h0m0s\";" +
                                    " TTL value is capped accordingly"]
            response['auth']['lease_duration'] = 60 * 60 * 5
            return MockResponse(response)
        return MockResponse(response)


def mock_get(url, **kwargs):
    assert kwargs['headers']['X-Vault-Token'] == tokens[-1]
    if(url.startswith('{}/v1/{}/azure/creds/openqa-role'.format(host, namespace))):
        lease_id = "azure/creds/openqa-role/{}".format(fake.uuid4())
        leases.append(lease_id)
        return MockResponse({
            "lease_id": lease_id,
            "lease_duration": 3600,
            "data": {"client_id": fake.uuid4(), "client_secret": fake.uuid4()},
        })
    elif(url.startswith('{}/v1/{}/secret/azure/openqa-role'.format(host, namespace))):
        return MockResponse({
            "data": {
                "subscription_id": "XXXXX-5127-52311-31221-XXXXXXXXX",
                "tenant_id": "XXXXXXX-ba41-4412-a321-XXXXXXXX"
            }
        })
    elif(url.startswith('{}/v1/{}/aws/creds/openqa-role'.format(host, namespace))):
        lease_id = "aws/creds/openqa-role/{}".format(fake.uuid4())
        leases.append(lease_id)
        return MockResponse({
            "lease_id": lease_id,
            "lease_duration": 3600,
            "data": {
                "access_key": fake.uuid4(),
                "secret_key": fake.uuid4(),
                "security_token": None
            }
        })

    elif(url.startswith('{}/v1/{}/gcp/key/openqa-role'.format(host, namespace))):
        keydata = """{{
  "type": "service_account",
  "project_id": "pcw",
  "private_key_id": "{}",
  "private_key": "{}",
  "client_email": "vaultopenqa-role-XXXXXXX@pcw.iam.gserviceaccount.com",
  "client_id": "{}",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/vaultopenqa-role-XXXXXXX%40pcw.iam.gservi\
ceaccount.com"
}}""".format(fake.uuid4(), fake.uuid4(), fake.uuid4())

        lease_id = "gcp/key/openqa-role/{}".format(fake.uuid4())
        leases.append(lease_id)
        return MockResponse({
            "lease_id": lease_id,
            "lease_duration": 3600,
            "data": {
                "key_algorithm": "KEY_ALG_RSA_2048",
                "key_type": "TYPE_GOOGLE_CREDENTIALS_FILE",
                "private_key_data": base64.b64encode(keydata.encode('UTF-8')).decode(encoding='UTF-8')
            }
        })


def set_pcw_ini():
    webui.settings.CONFIG_FILE = working_dir / 'pcw.ini'
    with open(webui.settings.CONFIG_FILE, "w") as f:
        f.write("""
[vault]
url = {}
user = devel
password = sag_ich_nicht
        """.format(host))


def test_Vault(monkeypatch):
    set_pcw_ini()
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "get", mock_get)

    v = Vault(namespace)
    assert v.url == 'http://foo.bar'
    assert v.user == 'devel'
    assert v.password == 'sag_ich_nicht'
    assert v.namespace == namespace

    assert v.getClientToken()['X-Vault-Token'] == tokens[-1]
    assert v.client_token_expire > (datetime.today() + timedelta(seconds=5))

    id_token = id(v.getClientToken())
    assert id_token == id(v.getClientToken())

    # fake client_token_expire to get new token
    v.client_token_expire = datetime.today()
    assert id_token != id(v.getClientToken())

    with pytest.raises(ConnectionError):
        v = Vault(namespace)
        v.user = 'Not_existing_user'
        v.getClientToken()

    with pytest.raises(NotImplementedError):
        v = Vault(namespace)
        v.getCredentials()

    v = Vault(namespace)
    assert v.renewClientToken(42) is None
    v.getClientToken()
    v.renewClientToken(42)
    v.renewClientToken(666 * 60 * 60)
    v.renewClientToken(55 * 60 * 60)


def test_AzureCredential(monkeypatch):
    set_pcw_ini()
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "get", mock_get)

    az = AzureCredential(namespace)
    assert az.getAuthExpire() is None
    az.revoke()
    assert az.isClientTokenExpired() is True
    assert az.isValid() is True

    client_id = az.getData()['client_id']
    assert client_id == az.getData()['client_id']
    assert az.getAuthExpire() > datetime.today()

    az.renew()
    assert client_id != az.getData()['client_id']
    az.revoke()


def test_Vault_revoke(monkeypatch):
    global leases
    set_pcw_ini()
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "get", mock_get)

    az = AzureCredential(namespace)
    az.getData()
    leases = list()
    az.revoke()

    az = AzureCredential(namespace)
    az.getData()
    with pytest.raises(ConnectionError):
        monkeypatch.setattr(requests, 'post', lambda x: 1/0)
        az.revoke()


def test_Vault_invalid_namespace(monkeypatch):
    set_pcw_ini()

    def with_errors(*args, **kargs):
        return MockResponse({'errors': ['bla CLEMIX', 'blub']}, status_code=404)

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, 'get', with_errors)

    az = AzureCredential("does_not_exists")
    with pytest.raises(ConnectionError):
        az.getData()


def test_EC2Credential(monkeypatch):
    set_pcw_ini()
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "get", mock_get)

    ec2 = EC2Credential(namespace)
    assert ec2.getAuthExpire() is None
    ec2.revoke()
    assert ec2.isClientTokenExpired() is True
    assert ec2.isValid() is True

    access_key = ec2.getData()['access_key']
    assert access_key == ec2.getData()['access_key']

    ec2.renew()
    assert access_key != ec2.getData()['access_key']
    ec2.revoke()
    ec2.revoke()


def test_GCECredential(monkeypatch):
    set_pcw_ini()
    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "get", mock_get)

    gce = GCECredential(namespace)
    assert gce.getAuthExpire() is None
    gce.revoke()
    assert gce.isClientTokenExpired() is True
    assert gce.isValid() is True

    private_key_id = gce.getPrivateKeyData()['private_key_id']
    assert private_key_id == gce.getData()['private_key_id']

    gce.renew()
    assert private_key_id != gce.getData()['private_key_id']
    gce.revoke()
    gce.revoke()

    file_a = gce.writetofile()
    file_a_content = ''
    with open(file_a, 'r') as f:
        file_a_content = f.read()

    assert gce.getPrivateKeyData() == json.loads(file_a_content)

    file_b = gce.writetofile()
    file_b_content = ''
    with open(file_b, 'r') as f:
        file_b_content = f.read()

    assert file_b_content == file_a_content
    assert gce._getAuthCacheFile() == Path('/tmp/pcw/GCECredential/{}/auth.json'.format(namespace))


def init_use_file_cache_test(monkeypatch):
    global authfile
    webui.settings.CONFIG_FILE = working_dir / 'pcw.ini'
    with open(webui.settings.CONFIG_FILE, "w") as f:
        f.write("""
[vault]
url = {}
user = devel
password = sag_ich_nicht
use-file-cache = True
        """.format(host))

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr(Vault, "_getAuthCacheFile", lambda x: working_dir / 'auth.json')
    if authfile.exists():
        authfile.unlink()


def test_Vault_use_file_cache(monkeypatch):

    def test_use_file_cache(monkeypatch, cred_class):
        global authfile
        init_use_file_cache_test(monkeypatch)
        assert not authfile.exists()

        cred = cred_class(namespace)
        cred.getData()
        assert authfile.exists()
        assert cred.auth_json == json.loads(authfile.read_text())

        cred_2 = cred_class(namespace)
        cred_2.getData()
        assert cred_2.auth_json == json.loads(authfile.read_text())
        assert cred_2.auth_json == cred.auth_json

        cred.renew()

        assert cred.auth_json == json.loads(authfile.read_text())
        assert cred_2.auth_json != json.loads(authfile.read_text())
        assert authfile.exists()

        del cred_2
        del cred
        assert authfile.exists()

    test_use_file_cache(monkeypatch, AzureCredential)
    test_use_file_cache(monkeypatch, EC2Credential)
    test_use_file_cache(monkeypatch, GCECredential)


def test_Vault_use_file_cache_errors(monkeypatch):
    global authfile
    init_use_file_cache_test(monkeypatch)

    with open(authfile, "w") as f:
        f.write('THIS_IS_NOT_JSON!!')

    assert authfile.exists()
    v = Vault(namespace)
    assert v.loadAuthCache() is None

    authfile.chmod(0o000)
    assert v.loadAuthCache() is None
    v.saveAuthCache()
