from webui.settings import PCWConfig
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from distutils.version import LooseVersion
import logging
import json
from pathlib import Path


class Provider:

    def __init__(self, namespace: str):
        self._namespace = namespace
        self.dry_run = PCWConfig.getBoolean('default/dry_run')
        self.logger = logging.getLogger(self.__module__)
        self.auth_json = self.read_auth_json()

    def read_auth_json(self):
        authcachepath = Path('/var/pcw/{}/{}.json'.format(self._namespace, self.__class__.__name__))
        if authcachepath.exists():
            self.log_info('Loading credentials')
            with authcachepath.open() as f:
                self.log_info("Try loading auth from file {}".format(f.name))
                return json.loads(f.read())
        else:
            self.log_err('Credentials not found in {}. Terminating', authcachepath)
            raise FileNotFoundError('Credentials not found')

    def getData(self, name):
        return self.auth_json[name]

    def older_than_min_age(self, age):
        return datetime.now(timezone.utc) > age + timedelta(
            hours=PCWConfig.get_feature_property('cleanup', 'min-image-age-hours', self._namespace))

    def needs_to_delete_image(self, order_number, image_date):
        if self.older_than_min_age(image_date):
            max_images_per_flavor = PCWConfig.get_feature_property('cleanup', 'max-images-per-flavor',
                                                                   self._namespace)
            max_image_age = image_date + timedelta(
                hours=PCWConfig.get_feature_property('cleanup', 'max-image-age-hours', self._namespace))
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
        self.logger.info("[{}] {}".format(self._namespace, message))

    def log_warn(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.warning("[{}] {}".format(self._namespace, message))

    def log_err(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.error("[{}] {}".format(self._namespace, message))

    def log_dbg(self,  message: str, *args: object):
        if args:
            message = message.format(*args)
        self.logger.debug("[{}] {}".format(self._namespace, message))


class Image:

    def __init__(self, name, flavor, build, date, img_id=None):
        self.name = name
        self.flavor = flavor
        self.build = build
        self.date = date
        self.id = img_id if img_id else name

    def __str__(self):
        return "[{} {} {} {}]".format(self.name, self.flavor, self.build, self.date)
