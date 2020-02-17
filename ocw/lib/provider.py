from webui.settings import ConfigFile
import re


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
        return type(e['default'])(cfg.get(
                [namespace_section, field],
                cfg.get([section, field], e['default'])))

    def parse_image_name_helper(self, img_name, regex_s, group_key=['version', 'flavor', 'type', 'arch'],
                                group_build=['kiwi', 'build']):
        for regex in regex_s:
            m = re.match(regex, img_name)
            if m:
                gdict = m.groupdict()
                return {
                    'key': '-'.join([gdict[k] for k in group_key if k in gdict and gdict[k] is not None]),
                    'build': "-".join([gdict[k] for k in group_build if k in gdict and gdict[k] is not None]),
                    }
        return None
