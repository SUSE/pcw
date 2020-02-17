from .provider import Provider
from .vault import EC2Credential
from distutils.version import LooseVersion
from dateutil.parser import parse
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import boto3
import re
import time
import logging

logger = logging.getLogger(__name__)


class EC2(Provider):
    __instances = dict()

    def __new__(cls, vault_namespace):
        if vault_namespace not in EC2.__instances:
            EC2.__instances[vault_namespace] = self = object.__new__(cls)
            self.__credentials = EC2Credential(vault_namespace)
            self.__ec2_client = dict()
            self.__ec2_resource = dict()
            self.__secret = None
            self.__key = None

        EC2.__instances[vault_namespace].check_credentials()
        return EC2.__instances[vault_namespace]

    def check_credentials(self):
        if self.__credentials.isValid():
            self.__credentials.renew()
            self.__key = None
            self.__secret = None
            self.__ec2_resource = dict()
            self.__ec2_client = dict()

        self.__secret = self.__credentials.getData('secret_key')
        self.__key = self.__credentials.getData('access_key')

        for i in range(1, 60 * 5):
            try:
                self.list_regions()
                return True
            except Exception:
                logger.info("check_credentials (attemp:%d) with key %s expiring at %s ",
                            i, self.__key, self.__credentials.getAuthExpire())
                time.sleep(1)
        self.list_regions()

    def ec2_resource(self, region='eu-central-1'):
        if region not in self.__ec2_resource:
            self.__ec2_resource[region] = boto3.resource('ec2', aws_access_key_id=self.__key,
                                                         aws_secret_access_key=self.__secret,
                                                         region_name=region)
        return self.__ec2_resource[region]

    def ec2_client(self, region='eu-central-1'):
        if region not in self.__ec2_client:
            self.__ec2_client[region] = boto3.client('ec2', aws_access_key_id=self.__key,
                                                     aws_secret_access_key=self.__secret,
                                                     region_name=region)
        return self.__ec2_client[region]

    def list_instances(self, region='eu-central-1'):
        return [i for i in self.ec2_resource(region).instances.all()]

    def list_regions(self):
        regions_resp = self.ec2_client().describe_regions()
        regions = [region['RegionName'] for region in regions_resp['Regions']]
        return regions

    def delete_instance(self, instance_id):
        self.ec2_resource().instances.filter(InstanceIds=[instance_id]).terminate()

    def parse_image_name(self, img_name):
        regexes = [
                   # openqa-SLES12-SP5-EC2.x86_64-0.9.1-BYOS-Build1.55.raw.xz
                   re.compile(r'''^openqa-SLES
                              (?P<version>\d+(-SP\d+)?)
                              -(?P<flavor>EC2)
                              \.
                              (?P<arch>[^-]+)
                              -
                              (?P<kiwi>\d+\.\d+\.\d+)
                              -
                              (?P<type>(BYOS|On-Demand))
                              -Build
                              (?P<build>\d+\.\d+)
                              \.raw\.xz
                              ''', re.RegexFlag.X),
                   # openqa-SLES15-SP2.x86_64-0.9.3-EC2-HVM-Build1.10.raw.xz'
                   # openqa-SLES15-SP2-BYOS.x86_64-0.9.3-EC2-HVM-Build1.10.raw.xz'
                   # openqa-SLES15-SP2.aarch64-0.9.3-EC2-HVM-Build1.49.raw.xz'
                   re.compile(r'''^openqa-SLES
                              (?P<version>\d+(-SP\d+)?)
                              (-(?P<type>[^\.]+))?
                              \.
                              (?P<arch>[^-]+)
                              -
                              (?P<kiwi>\d+\.\d+\.\d+)
                              -
                              (?P<flavor>EC2[-\w]+)
                              -Build
                              (?P<build>\d+\.\d+)
                              \.raw\.xz
                              ''', re.RegexFlag.X),
                   # openqa-SLES12-SP4-EC2-HVM-BYOS.x86_64-0.9.2-Build2.56.raw.xz'
                   re.compile(r'''^openqa-SLES
                              (?P<version>\d+(-SP\d+)?)
                              -
                              (?P<flavor>EC2[^\.]+)
                              \.
                              (?P<arch>[^-]+)
                              -
                              (?P<kiwi>\d+\.\d+\.\d+)
                              -
                              Build
                              (?P<build>\d+\.\d+)
                              \.raw\.xz
                              ''', re.RegexFlag.X)
                   ]
        return self.parse_image_name_helper(img_name, regexes)

    def cleanup_all(self):
        response = self.ec2_client().describe_images(Owners=['self'])
        images = dict()
        for img in response['Images']:
            # img is in the format described here:
            # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.describe_images
            logger.debug("[EC2] Found image '{}'".format(img['Name']))
            m = self.parse_image_name(img['Name'])
            if m:
                key = m['key']
                if key not in images:
                    images[key] = list()

                images[key].append({
                    'build': m['build'],
                    'name': img['Name'],
                    'creation_datetime':  parse(img['CreationDate']),
                    'id': img['ImageId'],
                    })
            else:
                logger.error("[EC2][{}] Unable to parse image name '{}'".format(
                    self.__credentials.namespace, img['Name']))

        for key in images:
            images[key].sort(key=lambda x: LooseVersion(x['build']))

        max_images_per_flavor = self.cfgGet('cleanup', 'max-images-per-flavor')
        max_images_age = datetime.now(timezone.utc) - timedelta(hours=self.cfgGet('cleanup', 'max-images-age-hours'))
        for img_list in images.values():
            for i in range(0, len(img_list)):
                img = img_list[i]
                if (i < len(img_list) - max_images_per_flavor or img['creation_datetime'] < max_images_age):
                    logger.info("[EC2] Delete image '{}' (ami:{})".format(img['name'], img['id']))
                    self.ec2_client().deregister_image(ImageId=img['id'], DryRun=False)
