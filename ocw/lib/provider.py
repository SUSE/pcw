from webui.settings import ConfigFile
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone


class Provider:

    def __init__(self, namespace):
        self.__namespace = namespace

    def cfgGet(self, section, field):
        mapping = {
            'cleanup/max-images-per-flavor': {'default': 1},
            'cleanup/max-image-age-hours': {'default': 24 * 31},
            'cleanup/min-image-age-hours': {'default': 24},
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

    def older_than_min_age(self, age):
        return datetime.now(timezone.utc) > age + timedelta(hours=self.cfgGet('cleanup', 'min-image-age-hours'))

    def needs_to_delete_image(self, order_number, image_date):
        if self.older_than_min_age(image_date):
            max_images_per_flavor = self.cfgGet('cleanup', 'max-images-per-flavor')
            max_image_age = image_date + timedelta(hours=self.cfgGet('cleanup', 'max-image-age-hours'))
            # order_number is starting from 0 and max_images_per_flavor is **amount**
            # so we need to increase order_number by 1 to be compare them
            return order_number+1 > max_images_per_flavor or max_image_age < datetime.now(timezone.utc)
        else:
            return False

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
