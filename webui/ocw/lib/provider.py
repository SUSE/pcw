from webui.settings import ConfigFile


class Provider:

    def __init__(self, namespace):
        self.__namespace = namespace

    def cfgGet(self, section, field):
        mapping = {
                'cleanup/max-images-per-flavor': {'default': 1},
                'cleanup/max-images-age-hours': {'default': 24 * 31},
                'cleanup/azure-storage-resourcegroup': {'default': 'openqa-upload'},
                'cleanup/azure-storage-account-name': {'default': 'openqa'},
                }
        key = '/'.join([section, field])
        if key not in mapping:
            raise LookupError("Missing {} in mapping list".format(key))
        e = mapping[key]
        namespace_section = '{}.namespace.{}'.format(section, self.__namespace)
        cfg = ConfigFile()
        return cfg.get(
                [namespace_section, field],
                cfg.get([section, field], e['default']))
