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
        self.__secret = self.get_data('secret_access_key')
        self.__key = self.get_data('access_key_id')

        for i in range(1, 5):
            try:
                self.get_all_regions()
                return
            except Exception:
                self.log_info(f"check_credentials (attempt:{i}) with key {self.__key}")
                time.sleep(1)
        raise ValueError("Invalid EC2 credentials")

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
            self.log_dbg(f"Found {len(response['Snapshots'])} snapshots in {region}")
            for snapshot in response['Snapshots']:
                if EC2.is_outdated(snapshot['StartTime'], valid_period_days):
                    if self.dry_run:
                        self.log_info(f"Snapshot deletion of {snapshot['SnapshotId']} skipped due to dry run mode")
                    else:
                        self.log_info(
                            f"Deleting snapshot {snapshot['SnapshotId']} in region {region} with StartTime={snapshot['StartTime']}"
                        )
                        try:
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
            self.log_dbg(f"Found {len(response['Volumes'])} volumes in {region}")
            for volume in response['Volumes']:
                if EC2.is_outdated(volume['CreateTime'], valid_period_days):
                    if self.volume_protected(volume):
                        self.log_info(f"Volume {volume['VolumeId']} has tag pcw_ignore so protected from deletion")
                    elif self.dry_run:
                        self.log_info(f"Volume deletion of {volume['VolumeId']} skipped due to dry run mode")
                    else:
                        self.log_info(f"Deleting volume {volume['VolumeId']} in region {region} with CreateTime={volume['CreateTime']}")
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
                self.log_info(f"Instance termination {instance_id} skipped due to dry run mode")
            else:
                self.log_info(f"Deleting {instance_id}", instance_id)
                self.ec2_resource(region).instances.filter(InstanceIds=[instance_id]).terminate()
        except ClientError as ex:
            if ex.response['Error']['Code'] == 'InvalidInstanceID.NotFound':
                self.log_warn(f"Failed to delete instance with id {instance_id}. It does not exists on EC2")
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
            self.log_info(f'{vpc} has no associated instances. Initializing cleanup of it')
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
                self.log_info('Delete VPC={}', vpc_id)
                self.ec2_resource(region).meta.client.delete_vpc(VpcId=vpc_id)
            return None
        except Exception as ex:
            return f"[{vpc_id}] {type(ex).__name__} on VPC deletion. {traceback.format_exc()}"

    def delete_vpc_subnets(self, vpc) -> None:
        self.log_dbg('Call delete_vpc_subnets')
        for subnet in vpc.subnets.all():
            for interface in subnet.network_interfaces.all():
                if self.dry_run:
                    self.log_info(f'Deletion of {interface} skipped due to dry_run mode')
                else:
                    self.log_info(f'Deleting {interface}')
                    interface.delete()
            if self.dry_run:
                self.log_info(f'Deletion of {subnet} skipped due to dry_run mode')
            else:
                self.log_info(f'Deleting {subnet}')
                subnet.delete()

    def delete_network_acls(self, vpc) -> None:
        self.log_dbg('Call delete_network_acls')
        for netacl in vpc.network_acls.all():
            if not netacl.is_default:
                if self.dry_run:
                    self.log_info(f'Deletion of {netacl} skipped due to dry_run mode')
                else:
                    self.log_info(f'Deleting {netacl}')
                    netacl.delete()

    def delete_vpc_peering_connections(self, region: str, vpc_id: str) -> None:
        self.log_dbg('Call delete_vpc_peering_connections')
        response = self.ec2_client(region).describe_vpc_peering_connections(
            Filters=[{'Name': 'requester-vpc-info.vpc-id', 'Values': [vpc_id]}])
        for vpcpeer in response['VpcPeeringConnections']:
            vpcpeer_connection = self.ec2_resource(region).VpcPeeringConnection(vpcpeer['VpcPeeringConnectionId'])
            if self.dry_run:
                self.log_info(f'Deletion of {vpcpeer_connection} skipped due to dry_run mode')
            else:
                self.log_info(f'Deleting {vpcpeer_connection}')
                vpcpeer_connection.delete()

    def delete_security_groups(self, vpc) -> None:
        self.log_dbg('Call delete_security_groups')
        for sgroup in vpc.security_groups.all():
            if sgroup.group_name != 'default':
                if self.dry_run:
                    self.log_info(f'Deletion of {sgroup} skipped due to dry_run mode')
                else:
                    self.log_info(f'Deleting {sgroup}')
                    sgroup.delete()

    def delete_vpc_endpoints(self, region, vpc_id):
        self.log_dbg('Call delete_vpc_endpoints')
        response = self.ec2_client(region).describe_vpc_endpoints(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        for end_point in response['VpcEndpoints']:
            if self.dry_run:
                self.log_info(f'Deletion of {end_point} skipped due to dry_run mode')
            else:
                self.log_info(f'Deleting {end_point}')
                self.ec2_client(region).delete_vpc_endpoints(VpcEndpointIds=[end_point['VpcEndpointId']])

    def delete_routing_tables(self, region: str, vpc_id: str) -> None:
        self.log_dbg('Call delete_routing_tables')
        vpc_filter = [{"Name": "vpc-id", "Values": [vpc_id]}]
        route_tables = self.ec2_client(region).describe_route_tables(Filters=vpc_filter)['RouteTables']
        self.log_dbg(f'Got {len(route_tables)} routing tables')
        for route_table in route_tables:
            for association in route_table['Associations']:
                if not association['Main']:
                    if self.dry_run:
                        self.log_info(
                            f"{association['RouteTableAssociationId']} disassociation with routing table won't happen due to dry_run mode"
                        )
                        self.log_dbg(association)
                    else:
                        self.log_info(f"{association['RouteTableAssociationId']} disassociation with routing table will happen")
                        self.log_dbg(association)
                        self.ec2_client(region).disassociate_route_table(AssociationId=association['RouteTableAssociationId'])
            for route in route_table['Routes']:
                if 'GatewayId' in route and route['GatewayId'] != 'local':
                    if self.dry_run:
                        self.log_info(f"{route_table['RouteTableId']} route will not be deleted due to dry_run mode")
                        self.log_dbg(route)
                    else:
                        self.log_info(f"Delete route {route_table['RouteTableId']}")
                        self.log_dbg(route)
                        self.ec2_client(region).delete_route(RouteTableId=route_table['RouteTableId'],
                                                             DestinationCidrBlock=route['DestinationCidrBlock'])
            if route_table['Associations'] == []:
                if self.dry_run:
                    self.log_info(f"{route_table['RouteTableId']} routing table will not be deleted due to dry_run mode")
                else:
                    self.log_info(f"Delete routing table {route_table['RouteTableId']}")
                    self.ec2_client(region).delete_route_table(RouteTableId=route_table['RouteTableId'])

    def delete_internet_gw(self, vpc) -> None:
        self.log_dbg('Call delete_internet_gw')
        for gate in vpc.internet_gateways.all():
            if self.dry_run:
                self.log_info(f'{gate} will be not deleted due to dry_run mode')
            else:
                self.log_info(f'Deleting {gate}')
                vpc.detach_internet_gateway(InternetGatewayId=gate.id)
                gate.delete()

    def cleanup_vpcs(self) -> None:
        self.log_dbg('Do cleanup of VPCs')
        vpc_errors = []
        vpc_notify = []
        vpc_locked = []
        vpc_known_exception = "botocore.exceptions.ClientError: An error occurred (DependencyViolation)"
        for region in self.all_regions:
            response = self.ec2_client(region).describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['false']}])
            self.log_dbg(f"Found {len(response['Vpcs'])} VPC's in {region}")
            for response_vpc in response['Vpcs']:
                vpc_id = response_vpc['VpcId']
                if self.volume_protected(response_vpc):
                    self.log_dbg(f'{vpc_id} has protection tag pcw_ignore obey the order!')
                    continue
                self.log_dbg(f"Found {vpc_id} in {region}. (OwnerId={response_vpc['OwnerId']}).")
                if PCWConfig.getBoolean('cleanup/vpc-notify-only', self._namespace):
                    vpc_notify.append(vpc_id)
                else:
                    resource_vpc = self.ec2_resource(region).Vpc(vpc_id)
                    if self.vpc_can_be_deleted(resource_vpc, vpc_id):
                        del_responce = self.delete_vpc(region, resource_vpc, vpc_id)
                        if del_responce is not None:
                            self.log_err(del_responce)
                            # Our cleanup is not perfect yet so often at this stage we have VPC's
                            # which has dependencies still and we don't want to have emails about this known problem
                            if vpc_known_exception not in del_responce:
                                vpc_errors.append(del_responce)
                    elif not self.dry_run:
                        vpc_locked.append(f'{vpc_id} (OwnerId={response_vpc["OwnerId"]}) in {region} is locked')
        self.report_cleanup_results(vpc_errors, vpc_notify, vpc_locked)

    def vpc_can_be_deleted(self, resource_vpc, vpc_id) -> bool:
        for subnet in resource_vpc.subnets.all():
            if len(list(subnet.instances.all())) > 0:
                self.log_info(f'{vpc_id} has associated instance(s) so can not be deleted')
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
            self.log_dbg(f"Found {len(response['Images'])} images in {region}")
            for img in response['Images']:
                if EC2.is_outdated(parse(img['CreationDate']), valid_period_days):
                    if self.dry_run:
                        self.log_info(f"Image deletion {img['ImageId']} skipped due to dry run mode")
                    else:
                        self.log_info(f"Delete image '{img['Name']}' (ami:{img['ImageId']})")
                        self.ec2_client(region).deregister_image(ImageId=img['ImageId'], DryRun=False)
