import configparser
import hashlib
import re

CONFIG_FILE = '/etc/pcw.ini'


class ConfigFile:

    __instance = None
    __file_hash = None
    filename = None
    config = None

    def __new__(cls, filename=None):
        if ConfigFile.__instance is None:
            ConfigFile.__instance = object.__new__(cls)
        ConfigFile.__instance.filename = filename or CONFIG_FILE
        return ConfigFile.__instance

    def get_hash(self):
        with open(self.filename, 'r') as f:
            h = hashlib.sha256()
            h.update(f.read().encode('utf-8'))
            return h.hexdigest()

    def check_file(self):
        file_hash = self.get_hash()
        if self.__file_hash is None or self.__file_hash != file_hash:
            self.__file_hash = file_hash
            self.config = configparser.ConfigParser()
            self.config.read(self.filename)

    def get(self, config_path: str, default=None):
        self.check_file()
        config_pointer = self.config
        config_array = config_path.split('/')
        for i in config_array:
            if i in config_pointer:
                config_pointer = config_pointer[i]
            else:
                if default is None:
                    raise LookupError('Missing attribute {} in file {}'.format(config_path, self.filename))
                return default
        return config_pointer

    def getList(self, config_path: str, default: list = []) -> list:
        return [i.strip() for i in self.get(config_path, ','.join(default)).split(',')]


class PCWConfig():

    @staticmethod
    def get_feature_property(feature: str, property: str, namespace: str = None):
        default_values = {
            'cleanup/max-age-hours': {'default': 24 * 7, 'return_type': int},
            'cleanup/azure-storage-resourcegroup': {'default': 'openqa-upload', 'return_type': str},
            'cleanup/azure-storage-account-name': {'default': 'openqa', 'return_type': str},
            'cleanup/ec2-max-age-days': {'default': -1, 'return_type': int},
            'updaterun/default_ttl': {'default': 44400, 'return_type': int},
            'notify/to': {'default': None, 'return_type': str},
            'notify/age-hours': {'default': 12, 'return_type': int},
            'cluster.notify/to': {'default': None, 'return_type': str},
            'notify/smtp': {'default': None, 'return_type': str},
            'notify/smtp-port': {'default': 25, 'return_type': int},
            'notify/from': {'default': 'pcw@publiccloud.qa.suse.de', 'return_type': str},
            'webui/openqa_url': {'default': 'https://openqa.suse.de', 'return_type': str}
        }
        key = '/'.join([feature, property])
        if key not in default_values:
            raise LookupError("Missing {} in default_values list".format(key))
        if namespace:
            setting = '{}.namespace.{}/{}'.format(feature, namespace, property)
            if PCWConfig.has(setting):
                return default_values[key]['return_type'](ConfigFile().get(setting))
        return default_values[key]['return_type'](
            ConfigFile().get(key, default_values[key]['default']))

    @staticmethod
    def get_namespaces_for(feature: str) -> list:
        if PCWConfig.has(feature):
            return ConfigFile().getList('{}/namespaces'.format(feature), ConfigFile().getList('default/namespaces'))
        return list()

    @staticmethod
    def get_providers_for(feature: str, namespace: str):
        return ConfigFile().getList('{}.namespace.{}/providers'.format(feature, namespace),
                                    ConfigFile().getList('{}/providers'.format(feature), ['EC2', 'AZURE', 'GCE']))

    @staticmethod
    def get_k8s_clusters_for_provider(namespace: str, provider: str) -> list:
        result = []
        clusters = ConfigFile().get(f"k8sclusters.namespace.{namespace}/{provider}-clusters")
        for cluster in clusters.split(','):
            cluster = cluster.strip()
            if not re.match(r'^[\w-]+:[\w-]+$', cluster):
                raise ValueError(f"Invalid cluster pair '{cluster}' in config file. "
                                 "Must be like 'resource_group:cluster_name'")
            resource_group, cluster_name = cluster.split(':')
            result.append({'resource_group': resource_group, 'cluster_name': cluster_name})
        return result

    @staticmethod
    def has(setting: str) -> bool:
        try:
            ConfigFile().get(setting)
            return True
        except LookupError:
            return False

    @staticmethod
    def getBoolean(config_path: str, namespace: str = None, default=False) -> bool:
        if namespace:
            (feature, property) = config_path.split('/')
            setting = '{}.namespace.{}/{}'.format(feature, namespace, property)
            if PCWConfig.has(setting):
                value = ConfigFile().get(setting)
            else:
                value = ConfigFile().get(config_path, default)
        else:
            value = ConfigFile().get(config_path, default)
        if isinstance(value, bool):
            return value
        return bool(re.match("^(true|on|1|yes)$", str(value), flags=re.IGNORECASE))
