import traceback
import time
from datetime import date, datetime, timedelta
from typing import Dict
import boto3
from botocore.exceptions import ClientError
from dateutil.parser import parse
from webui.PCWConfig import PCWConfig, ConfigFile
from ocw.lib.emailnotify import send_mail
from .provider import Provider
from ..models import Instance


class EC2(Provider):
    __instances: Dict[str, "EC2"] = {}
    default_region: str = 'eu-central-1'

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.check_credentials()
        if PCWConfig.has('default/ec2_regions'):
            self.all_regions = ConfigFile().getList('default/ec2_regions')
        else:
            self.all_regions = self.get_all_regions()

    def __new__(cls, vault_namespace: str):
        if vault_namespace not in EC2.__instances:
            EC2.__instances[vault_namespace] = self = object.__new__(cls)
            self.__ec2_client = {}
            self.__ec2_resource = {}
            self.__secret = None
            self.__key = None

        return EC2.__instances[vault_namespace]

    def check_credentials(self) -> None:

        self.__secret = self.get_data('secret_key')
        self.__key = self.get_data('access_key')

        for i in range(1, 5):
            try:
                self.get_all_regions()
            except Exception:
                self.log_info("check_credentials (attemp:{}) with key {}", i, self.__key)
                time.sleep(1)
        self.get_all_regions()

    def ec2_resource(self, region: str) -> "boto3.session.Session.resource":
        if region not in self.__ec2_resource:
            self.__ec2_resource[region] = boto3.resource('ec2', aws_access_key_id=self.__key,
                                                         aws_secret_access_key=self.__secret,
                                                         region_name=region)
        return self.__ec2_resource[region]

    def ec2_client(self, region: str) -> "boto3.session.Session.client":
        if region not in self.__ec2_client:
            self.__ec2_client[region] = boto3.client('ec2', aws_access_key_id=self.__key,
                                                     aws_secret_access_key=self.__secret,
                                                     region_name=region)
        return self.__ec2_client[region]

    @staticmethod
    def is_outdated(creation_time: datetime, valid_period_days: float) -> bool:
        return datetime.date(creation_time) < (date.today() - timedelta(days=valid_period_days))

    def cleanup_snapshots(self, valid_period_days: float) -> None:
        self.log_dbg("Call clean_snapshots")
        for region in self.all_regions:
            response = self.ec2_client(region).describe_snapshots(OwnerIds=['self'])
            self.log_dbg("Found {} snapshots in {}", len(response['Snapshots']), region)
            for snapshot in response['Snapshots']:
                if EC2.is_outdated(snapshot['StartTime'], valid_period_days):
                    try:
                        if self.dry_run:
                            self.log_info("Snapshot deletion of {} skipped due to dry run mode",
                                          snapshot['SnapshotId'])
                        else:
                            self.log_info("Deleting snapshot {} in region {} with StartTime={}",
                                          snapshot['SnapshotId'], region, snapshot['StartTime'])
                            self.ec2_client(region).delete_snapshot(SnapshotId=snapshot['SnapshotId'])
                    except ClientError as ex:
                        if ex.response['Error']['Code'] == 'InvalidSnapshot.InUse':
                            self.log_info(ex.response['Error']['Message'])
                        else:
                            raise ex

    def cleanup_volumes(self, valid_period_days: float) -> None:
        self.log_dbg("Call cleanup_volumes")
        for region in self.all_regions:
            response = self.ec2_client(region).describe_volumes()
            self.log_dbg("Found {} volumes in {}", len(response['Volumes']), region)
            for volume in response['Volumes']:
                if EC2.is_outdated(volume['CreateTime'], valid_period_days):
                    if self.volume_protected(volume):
                        self.log_info('Volume {} has tag pcw_ignore so protected from deletion',
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

    def volume_protected(self, volume: dict) -> bool:
        if 'Tags' in volume:
            for tag in volume['Tags']:
                if tag['Key'] == Instance.TAG_IGNORE:
                    return True
        return False

    def list_instances(self, region: str) -> list:
        return list(self.ec2_resource(region).instances.all())

    def get_all_regions(self) -> list:
        regions_resp = self.ec2_client(EC2.default_region).describe_regions()
        regions = [region['RegionName'] for region in regions_resp['Regions']]
        return regions

    def delete_instance(self, region: str, instance_id: str):
        try:
            if self.dry_run:
                self.log_info("Instance termination {} skipped due to dry run mode", instance_id)
            else:
                self.log_info("Deleting {}", instance_id)
                self.ec2_resource(region).instances.filter(InstanceIds=[instance_id]).terminate()
        except ClientError as ex:
            if ex.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                self.log_warn("Failed to delete instance with id {}. It does not exists on EC2", instance_id)
            else:
                raise ex

    def cleanup_all(self) -> None:
        valid_period_days = PCWConfig.get_feature_property('cleanup', 'ec2-max-age-days', self._namespace)

        if valid_period_days > 0:
            self.log_info("Do cleanup of images, snapshots and volumes")
            self.cleanup_images(valid_period_days)
            self.cleanup_snapshots(valid_period_days)
            self.cleanup_volumes(valid_period_days)
        if PCWConfig.getBoolean('cleanup/vpc_cleanup', self._namespace):
            self.cleanup_vpcs()

    def delete_vpc(self, region: str, vpc, vpc_id: str):
        try:
            self.log_info('{} has no associated instances. Initializing cleanup of it', vpc)
            self.delete_routing_tables(region, vpc_id)
            self.delete_security_groups(vpc)
            self.delete_network_acls(vpc)
            self.delete_vpc_subnets(vpc)
            self.delete_internet_gw(vpc)
            self.delete_vpc_endpoints(region, vpc_id)
            self.delete_vpc_peering_connections(region, vpc_id)
            if self.dry_run:
                self.log_info('Deletion of VPC skipped due to dry_run mode')
            else:
                # finally, delete the vpc
                self.ec2_resource(region).meta.client.delete_vpc(VpcId=vpc_id)
            return None
        except Exception as ex:
            return f"[{vpc_id}]{type(ex).__name__} on VPC deletion. {traceback.format_exc()}"

    def delete_vpc_subnets(self, vpc) -> None:
        self.log_dbg('Call delete_vpc_subnets')
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

    def delete_network_acls(self, vpc) -> None:
        self.log_dbg('Call delete_network_acls')
        for netacl in vpc.network_acls.all():
            if not netacl.is_default:
                if self.dry_run:
                    self.log_info('Deletion of {} skipped due to dry_run mode', netacl)
                else:
                    self.log_info('Deleting {}', netacl)
                    netacl.delete()

    def delete_vpc_peering_connections(self, region: str, vpc_id: str) -> None:
        self.log_dbg('Call delete_vpc_peering_connections')
        response = self.ec2_client(region).describe_vpc_peering_connections(
            Filters=[{'Name': 'requester-vpc-info.vpc-id', 'Values': [vpc_id]}])
        for vpcpeer in response['VpcPeeringConnections']:
            vpcpeer_connection = self.ec2_resource(region).VpcPeeringConnection(vpcpeer['VpcPeeringConnectionId'])
            if self.dry_run:
                self.log_info('Deletion of {} skipped due to dry_run mode', vpcpeer_connection)
            else:
                self.log_info('Deleting {}', vpcpeer_connection)
                vpcpeer_connection.delete()

    def delete_security_groups(self, vpc) -> None:
        self.log_dbg('Call delete_security_groups')
        for sgroup in vpc.security_groups.all():
            if sgroup.group_name != 'default':
                if self.dry_run:
                    self.log_info('Deletion of {} skipped due to dry_run mode', sgroup)
                else:
                    self.log_info('Deleting {}', sgroup)
                    sgroup.delete()

    def delete_vpc_endpoints(self, region, vpc_id):
        self.log_dbg('Call delete_vpc_endpoints')
        response = self.ec2_client(region).describe_vpc_endpoints(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        for end_point in response['VpcEndpoints']:
            if self.dry_run:
                self.log_info('Deletion of {} skipped due to dry_run mode', end_point)
            else:
                self.log_info('Deleting {}', end_point)
                self.ec2_client(region).delete_vpc_endpoints(VpcEndpointIds=[end_point['VpcEndpointId']])

    def delete_routing_tables(self, region: str, vpc_id: str) -> None:
        self.log_dbg('Call delete_routing_tables')
        vpc_filter = [{"Name": "vpc-id", "Values": [vpc_id]}]
        route_tables = self.ec2_client(region).describe_route_tables(Filters=vpc_filter)['RouteTables']
        self.log_dbg('Got {} routing tables', len(route_tables))
        for route_table in route_tables:
            for association in route_table['Associations']:
                if not association['Main']:
                    if self.dry_run:
                        self.log_info('{} disassociation with routing table won\'t happen due to dry_run mode',
                                      association['RouteTableAssociationId'])
                    else:
                        self.log_info('{} disassociation with routing table will happen',
                                      association['RouteTableAssociationId'])
                        self.ec2_client(region).disassociate_route_table(AssociationId=association['RouteTableAssociationId'])
            for route in route_table['Routes']:
                if 'GatewayId' in route and route['GatewayId'] != 'local':
                    if self.dry_run:
                        self.log_info('{} route will not be deleted due to dry_run mode', route_table)
                    else:
                        self.log_info('{} route will be deleted', route_table)
                        self.ec2_client(region).delete_route(RouteTableId=route_table['RouteTableId'],
                                                             DestinationCidrBlock=route['DestinationCidrBlock'])
            if route_table['Associations'] == []:
                if self.dry_run:
                    self.log_info('{} routing table will not be deleted due to dry_run mode', route_table['RouteTableId'])
                else:
                    self.log_info('{} routing table will be deleted due to dry_run mode', route_table['RouteTableId'])
                    self.ec2_client(region).delete_route_table(RouteTableId=route_table['RouteTableId'])

    def delete_internet_gw(self, vpc) -> None:
        self.log_dbg('Call delete_internet_gw')
        for gate in vpc.internet_gateways.all():
            if self.dry_run:
                self.log_info('{} will be not deleted due to dry_run mode', gate)
            else:
                self.log_info('Deleting {}', gate)
                vpc.detach_internet_gateway(InternetGatewayId=gate.id)
                gate.delete()

    def cleanup_vpcs(self) -> None:
        self.log_dbg('Do cleanup of VPCs')
        vpc_errors = []
        vpc_notify = []
        vpc_locked = []
        for region in self.all_regions:
            response = self.ec2_client(region).describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['false']}])
            self.log_dbg("Found {} VPC\'s in {}", len(response['Vpcs']), region)
            for response_vpc in response['Vpcs']:
                vpc_id = response_vpc['VpcId']
                if self.volume_protected(response_vpc):
                    self.log_dbg('{} has protection tag pcw_ignore obey the order!', vpc_id)
                    continue
                self.log_dbg('Found {} in {}. (OwnerId={}).', vpc_id, region, response_vpc['OwnerId'])
                if PCWConfig.getBoolean('cleanup/vpc-notify-only', self._namespace):
                    vpc_notify.append(vpc_id)
                else:
                    resource_vpc = self.ec2_resource(region).Vpc(vpc_id)
                    if self.vpc_can_be_deleted(resource_vpc, vpc_id):
                        del_responce = self.delete_vpc(region, resource_vpc, vpc_id)
                        if del_responce is not None:
                            self.log_err(del_responce)
                            vpc_errors.append(del_responce)
                    elif not self.dry_run:
                        vpc_locked.append(f'{vpc_id} (OwnerId={response_vpc["OwnerId"]}) in {region} is locked')
        self.report_cleanup_results(vpc_errors, vpc_notify, vpc_locked)

    def vpc_can_be_deleted(self, resource_vpc, vpc_id) -> bool:
        for subnet in resource_vpc.subnets.all():
            if len(list(subnet.instances.all())) > 0:
                self.log_info('{} has associated instance(s) so can not be deleted', vpc_id)
                return False
        return True

    def report_cleanup_results(self, vpc_errors: list, vpc_notify: list, vpc_locked: list) -> None:
        if len(vpc_errors) > 0:
            send_mail(f'Errors on VPC deletion in [{self._namespace}]', '\n'.join(vpc_errors))
        if len(vpc_notify) > 0:
            send_mail(f'{len(vpc_notify)} VPC\'s should be deleted, skipping due vpc-notify-only=True', ','.join(vpc_notify))
        if len(vpc_locked) > 0:
            send_mail('VPC deletion locked by running VMs', '\n'.join(vpc_locked))

    def cleanup_images(self, valid_period_days: float) -> None:
        self.log_dbg('Call cleanup_images')
        for region in self.all_regions:
            response = self.ec2_client(region).describe_images(Owners=['self'])
            self.log_dbg("Found {} images in {}", len(response['Images']), region)
            for img in response['Images']:
                if EC2.is_outdated(parse(img['CreationDate']), valid_period_days):
                    if self.dry_run:
                        self.log_info("Image deletion {} skipped due to dry run mode", img['ImageId'])
                    else:
                        self.log_info("Delete image '{}' (ami:{})".format(img['Name'], img['ImageId']))
                        self.ec2_client(region).deregister_image(ImageId=img['ImageId'], DryRun=False)
