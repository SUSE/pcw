from .provider import Provider, Image
from webui.settings import PCWConfig
from .vault import EC2Credential
from dateutil.parser import parse
import boto3
from botocore.exceptions import ClientError
import re
from datetime import date, datetime, timedelta
from ocw.lib.emailnotify import send_mail
import traceback
import time


class EC2(Provider):
    __instances = dict()
    default_region = 'eu-central-1'

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.check_credentials()
        self.all_regions = self.get_all_regions()

    def __new__(cls, vault_namespace):
        if vault_namespace not in EC2.__instances:
            EC2.__instances[vault_namespace] = self = object.__new__(cls)
            self.__credentials = EC2Credential(vault_namespace)
            self.__ec2_client = dict()
            self.__eks_client = dict()
            self.__ec2_resource = dict()
            self.__secret = None
            self.__key = None

        return EC2.__instances[vault_namespace]

    def check_credentials(self):
        if self.__credentials.isExpired():
            self.__credentials.renew()
            self.__key = None
            self.__secret = None
            self.__ec2_resource = dict()
            self.__ec2_client = dict()
            self.__eks_client = dict()

        self.__secret = self.__credentials.getData('secret_key')
        self.__key = self.__credentials.getData('access_key')

        for i in range(1, 60 * 5):
            try:
                self.get_all_regions()
                return True
            except Exception:
                self.log_info("check_credentials (attemp:{}) with key {} expiring at {} ", i, self.__key,
                              self.__credentials.getAuthExpire())
                time.sleep(1)
        self.get_all_regions()

    def ec2_resource(self, region):
        if region not in self.__ec2_resource:
            self.__ec2_resource[region] = boto3.resource('ec2', aws_access_key_id=self.__key,
                                                         aws_secret_access_key=self.__secret,
                                                         region_name=region)
        return self.__ec2_resource[region]

    def ec2_client(self, region):
        if region not in self.__ec2_client:
            self.__ec2_client[region] = boto3.client('ec2', aws_access_key_id=self.__key,
                                                     aws_secret_access_key=self.__secret,
                                                     region_name=region)
        return self.__ec2_client[region]

    def eks_client(self, region):
        if region not in self.__eks_client:
            self.__eks_client[region] = boto3.client('eks', aws_access_key_id=self.__key,
                                                     aws_secret_access_key=self.__secret,
                                                     region_name=region)
        return self.__eks_client[region]

    def all_clusters(self):
        clusters = list()
        for region in self.all_regions:
            response = self.eks_client(region).list_clusters()
            [clusters.append(cluster) for cluster in response['clusters']]
        return clusters

    @staticmethod
    def needs_to_delete_snapshot(snapshot, cleanup_ec2_max_snapshot_age_days) -> bool:
        delete_older_than = date.today() - timedelta(days=cleanup_ec2_max_snapshot_age_days)
        if datetime.date(snapshot['StartTime']) < delete_older_than:
            regexes = [
                re.compile(r'''^OpenQA upload image$'''),
                re.compile(r'''^Created by CreateImage\([\w-]+\) for ami-\w+ from vol-\w+$''')
            ]
            for regex in regexes:
                m = re.match(regex, snapshot['Description'].strip())
                if m:
                    return True
        return False

    def cleanup_snapshots(self, cleanup_ec2_max_snapshot_age_days):
        for region in self.all_regions:
            response = self.ec2_client(region).describe_snapshots(OwnerIds=['self'])
            response['Snapshots'].sort(key=lambda snapshot: snapshot['StartTime'].timestamp())
            for snapshot in response['Snapshots']:
                if EC2.needs_to_delete_snapshot(snapshot, cleanup_ec2_max_snapshot_age_days):
                    self.log_info("Deleting snapshot {} in region {} with StartTime={}", snapshot['SnapshotId'],
                                  region, snapshot['StartTime'])
                    try:
                        if self.dry_run:
                            self.log_info("Snapshot deletion of {} skipped due to dry run mode",
                                          snapshot['SnapshotId'])
                        else:
                            self.ec2_client(region).delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    except ClientError as ex:
                        if ex.response['Error']['Code'] == 'InvalidSnapshot.InUse':
                            self.log_info(ex.response['Error']['Message'])
                        else:
                            raise ex

    def cleanup_volumes(self, cleanup_ec2_max_volumes_age_days):
        delete_older_than = date.today() - timedelta(days=cleanup_ec2_max_volumes_age_days)
        for region in self.all_regions:
            response = self.ec2_client(region).describe_volumes()
            for volume in response['Volumes']:
                if datetime.date(volume['CreateTime']) < delete_older_than:
                    if self.volume_protected(volume):
                        self.log_info('Volume {} has tag DO_NOT_DELETE so protected from deletion',
                                      volume['VolumeId'])
                    elif self.dry_run:
                        self.log_info("Volume deletion of {} skipped due to dry run mode", volume['VolumeId'])
                    else:
                        self.log_info("Deleting volume {} in region {} with CreateTime={}", volume['VolumeId'], region,
                                      volume['CreateTime'])
                        try:
                            self.ec2_client(region).delete_volume(VolumeId=volume['VolumeId'])
                        except ClientError as ex:
                            if ex.response['Error']['Code'] == 'VolumeInUse':
                                self.log_info(ex.response['Error'])
                            else:
                                raise ex

    def volume_protected(self, volume):
        if 'Tags' in volume:
            for tag in volume['Tags']:
                if tag['Key'] == 'DO_NOT_DELETE':
                    return True
        return False

    def list_instances(self, region):
        return [i for i in self.ec2_resource(region).instances.all()]

    def get_all_regions(self):
        regions_resp = self.ec2_client(EC2.default_region).describe_regions()
        regions = [region['RegionName'] for region in regions_resp['Regions']]
        return regions

    def delete_instance(self, region, instance_id):
        try:
            if self.dry_run:
                self.log_info("Instance termination {} skipped due to dry run mode", instance_id)
            else:
                self.ec2_resource(region).instances.filter(InstanceIds=[instance_id]).terminate()
        except ClientError as ex:
            if ex.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                self.log_warn("Failed to delete instance with id {}. It does not exists on EC2", instance_id)
            else:
                raise ex

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
                              (?P<flavor>EC2[-\w]*)
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
        cleanup_ec2_max_snapshot_age_days = PCWConfig.get_feature_property('cleanup', 'ec2-max-snapshot-age-days',
                                                                           self._namespace)
        cleanup_ec2_max_volumes_age_days = PCWConfig.get_feature_property('cleanup', 'ec2-max-volumes-age-days',
                                                                          self._namespace)
        self.cleanup_images()
        if cleanup_ec2_max_snapshot_age_days >= 0:
            self.cleanup_snapshots(cleanup_ec2_max_snapshot_age_days)
        if cleanup_ec2_max_volumes_age_days >= 0:
            self.cleanup_volumes(cleanup_ec2_max_volumes_age_days)
        if PCWConfig.getBoolean('cleanup/vpc_cleanup', self._namespace):
            self.cleanup_uploader_vpcs()

    def delete_vpc(self, region, vpc, vpcId):
        try:
            self.log_info('{} has no associated instances. Initializing cleanup of it', vpc)
            self.delete_internet_gw(vpc)
            self.delete_routing_tables(vpc)
            self.delete_vpc_endpoints(region, vpcId)
            self.delete_security_groups(vpc)
            self.delete_vpc_peering_connections(region, vpcId)
            self.delete_network_acls(vpc)
            self.delete_vpc_subnets(vpc)
            if self.dry_run:
                self.log_info('Deletion of VPC skipped due to dry_run mode')
            else:
                # finally, delete the vpc
                self.ec2_resource(region).meta.client.delete_vpc(VpcId=vpcId)
        except Exception as e:
            self.log_err("{} on VPC deletion. {}", type(e).__name__, traceback.format_exc())
            send_mail('{} on VPC deletion in [{}]'.format(type(e).__name__, self._namespace), traceback.format_exc())

    def delete_vpc_subnets(self, vpc):
        for subnet in vpc.subnets.all():
            for interface in subnet.network_interfaces.all():
                if self.dry_run:
                    self.log_info('Deletion of {} skipped due to dry_run mode', interface)
                else:
                    self.log_info('Deleting {}', interface)
                    interface.delete()
            if self.dry_run:
                self.log_info('Deletion of {} skipped due to dry_run mode', subnet)
            else:
                self.log_info('Deleting {}', subnet)
                subnet.delete()

    def delete_network_acls(self, vpc):
        for netacl in vpc.network_acls.all():
            if not netacl.is_default:
                if self.dry_run:
                    self.log_info('Deletion of {} skipped due to dry_run mode', netacl)
                else:
                    self.log_info('Deleting {}', netacl)
                    netacl.delete()

    def delete_vpc_peering_connections(self, region, vpcId):
        response = self.ec2_client(region).describe_vpc_peering_connections(
            Filters=[{'Name': 'requester-vpc-info.vpc-id', 'Values': [vpcId]}])
        for vpcpeer in response['VpcPeeringConnections']:
            vpcpeer_connection = self.ec2_resource(region).VpcPeeringConnection(vpcpeer['VpcPeeringConnectionId'])
            if self.dry_run:
                self.log_info('Deletion of {} skipped due to dry_run mode', vpcpeer_connection)
            else:
                self.log_info('Deleting {}', vpcpeer_connection)
                vpcpeer_connection.delete()

    def delete_security_groups(self, vpc):
        for sg in vpc.security_groups.all():
            if sg.group_name != 'default':
                if self.dry_run:
                    self.log_info('Deletion of {} skipped due to dry_run mode', sg)
                else:
                    self.log_info('Deleting {}', sg)
                    sg.delete()

    def delete_vpc_endpoints(self, region, vpcId):
        response = self.ec2_client(region).describe_vpc_endpoints(Filters=[{'Name': 'vpc-id', 'Values': [vpcId]}])
        for ep in response['VpcEndpoints']:
            if self.dry_run:
                self.log_info('Deletion of {} skipped due to dry_run mode', ep)
            else:
                self.log_info('Deleting {}', ep)
                self.ec2_client(region).delete_vpc_endpoints(VpcEndpointIds=[ep['VpcEndpointId']])

    def delete_routing_tables(self, vpc):
        for rt in vpc.route_tables.all():
            # we can not delete main RouteTable's , not main one don't have associations_attributes
            if len(rt.associations_attribute) == 0:
                if self.dry_run:
                    self.log_info('{} will be not deleted due to dry_run mode', rt)
                else:
                    self.log_info('Deleting {}', rt)
                    rt.delete()

    def delete_internet_gw(self, vpc):
        for gw in vpc.internet_gateways.all():
            if self.dry_run:
                self.log_info('{} will be not deleted due to dry_run mode', gw)
            else:
                self.log_info('Deleting {}', gw)
                vpc.detach_internet_gateway(InternetGatewayId=gw.id)
                gw.delete()

    def cleanup_uploader_vpcs(self):
        for region in self.all_regions:
            response = self.ec2_client(region).describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['false']},
                                                                      {'Name': 'tag:Name', 'Values': ['uploader-*']}])
            for response_vpc in response['Vpcs']:
                self.log_info('{} in {} looks like uploader leftover. (OwnerId={}).', response_vpc['VpcId'], region,
                              response_vpc['OwnerId'])
                if PCWConfig.getBoolean('cleanup/vpc-notify-only', self._namespace):
                    send_mail('VPC {} should be deleted, skipping due vpc-notify-only=True'.format(
                        response_vpc['VpcId']), '')
                else:
                    resource_vpc = self.ec2_resource(region).Vpc(response_vpc['VpcId'])
                    can_be_deleted = True
                    for subnet in resource_vpc.subnets.all():
                        if len(list(subnet.instances.all())):
                            self.log_warn('{} has associated instance(s) so can not be deleted',
                                          response_vpc['VpcId'])
                            can_be_deleted = False
                            break
                    if can_be_deleted:
                        self.delete_vpc(region, resource_vpc, response_vpc['VpcId'])
                    elif not self.dry_run:
                        body = 'Uploader leftover {} (OwnerId={}) in {} is locked'.format(response_vpc['VpcId'],
                                                                                          response_vpc['OwnerId'],
                                                                                          region)
                        send_mail('VPC deletion locked by running VMs', body)

    def cleanup_images(self):
        for region in self.all_regions:
            response = self.ec2_client(region).describe_images(Owners=['self'])
            images = list()
            for img in response['Images']:
                # img is in the format described here:
                # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2.html#EC2.Client.describe_images
                m = self.parse_image_name(img['Name'])
                if m:
                    self.log_dbg("Image {} is candidate for deletion with build {}", img['Name'], m['build'])
                    images.append(
                        Image(img['Name'], flavor=m['key'], build=m['build'], date=parse(img['CreationDate']),
                              img_id=img['ImageId']))
                else:
                    self.log_err(" Unable to parse image name '{}'", img['Name'])
            keep_images = self.get_keeping_image_names(images)
            for img in [i for i in images if i.name not in keep_images]:
                self.log_dbg("Delete image '{}' (ami:{})".format(img.name, img.id))
                if self.dry_run:
                    self.log_info("Image deletion {} skipped due to dry run mode", img.id)
                else:
                    self.ec2_client(region).deregister_image(ImageId=img.id, DryRun=False)
