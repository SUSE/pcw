from webui.settings import ConfigFile
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from distutils.version import LooseVersion
import logging


class Provider:

    def __init__(self, namespace: str):
        self.__namespace = namespace
        self.dry_run = ConfigFile().getBoolean('default/dry_run', False)
        self.logger = logging.getLogger(self.__module__)

    def cfgGet(self, section: str, field: str):
        default_values = {
            'cleanup/max-images-per-flavor': 1,
            'cleanup/max-image-age-hours': 24 * 31,
            'cleanup/min-image-age-hours': 24,
            'cleanup/azure-storage-resourcegroup': 'openqa-upload',
            'cleanup/azure-storage-account-name': 'openqa',
            'cleanup/ec2-max-snapshot-age-days': -1,
        }
        key = '/'.join([section, field])
        if key not in default_values:
            raise LookupError("Missing {} in default_values list".format(key))
        default = default_values[key]
        namespace_section = '{}.namespace.{}'.format(section, self.__namespace)
        return type(default)(ConfigFile().get('{}/{}'.format(namespace_section, field),
                                              ConfigFile().get('{}/{}'.format(section, field), default)))

    def older_than_min_age(self, age):
        return datetime.now(timezone.utc) > age + timedelta(hours=self.cfgGet('cleanup', 'min-image-age-hours'))

    def needs_to_delete_image(self, order_number, image_date):
        if self.older_than_min_age(image_date):
            max_images_per_flavor = self.cfgGet('cleanup', 'max-images-per-flavor')
            max_image_age = image_date + timedelta(hours=self.cfgGet('cleanup', 'max-image-age-hours'))
            return order_number >= max_images_per_flavor or max_image_age < datetime.now(timezone.utc)
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

    def get_keeping_image_names(self, images):
        images_by_flavor = dict()
        for img in images:
            if (img.flavor not in images_by_flavor):
                images_by_flavor[img.flavor] = list()
            images_by_flavor[img.flavor].append(img)

        keep_images = list()
        for img_list in [images_by_flavor[x] for x in sorted(images_by_flavor)]:
            img_list.sort(key=lambda x: LooseVersion(x.build), reverse=True)
            for i in range(0, len(img_list)):
                img = img_list[i]
                if (not self.needs_to_delete_image(i, img.date)):
                    keep_images.append(img.name)

        return keep_images

    def log_info(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.info("[{}] {}".format(self.__namespace, message))

    def log_warn(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.warning("[{}] {}".format(self.__namespace, message))

    def log_err(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.error("[{}] {}".format(self.__namespace, message))

    def log_dbg(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.debug("[{}] {}".format(self.__namespace, message))


class Image:

    def __init__(self, name, flavor, build, date, img_id=None):
        self.name = name
        self.flavor = flavor
        self.build = build
        self.date = date
        self.id = img_id if img_id else name

    def __str__(self):
        return "[{} {} {} {}]".format(self.name, self.flavor, self.build, self.date)
