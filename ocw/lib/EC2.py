import traceback
import time
from datetime import date, datetime, timedelta, timezone
import boto3
from botocore.exceptions import ClientError
from dateutil.parser import parse
from webui.settings import PCWConfig, ConfigFile
from ocw.lib.emailnotify import send_mail
from .provider import Provider


class EC2(Provider):
    __instances = {}
    default_region = 'eu-central-1'

    def __init__(self, namespace: str):
        super().__init__(namespace)
        self.check_credentials()
        if PCWConfig.has('default/ec2_regions'):
            self.all_regions = ConfigFile().getList('default/ec2_regions')
        else:
            self.all_regions = self.get_all_regions()
        if PCWConfig.has('clusters/ec2_regions'):
            self.cluster_regions = ConfigFile().getList('clusters/ec2_regions')
        else:
            self.cluster_regions = self.get_all_regions()

    def __new__(cls, vault_namespace):
        if vault_namespace not in EC2.__instances:
            EC2.__instances[vault_namespace] = self = object.__new__(cls)
            self.__ec2_client = {}
            self.__eks_client = {}
            self.__ec2_resource = {}
            self.__secret = None
            self.__key = None

        return EC2.__instances[vault_namespace]

    def check_credentials(self):

        self.__secret = self.get_data('secret_key')
        self.__key = self.get_data('access_key')

        for i in range(1, 5):
            try:
                self.get_all_regions()
                return True
            except Exception:
                self.log_info("check_credentials (attemp:{}) with key {}", i, self.__key)
                time.sleep(1)
        self.get_all_regions()
        return True

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
        clusters = {}
        for region in self.cluster_regions:
            response = self.eks_client(region).list_clusters()
            if 'clusters' in response and len(response['clusters']) > 0:
                clusters[region] = []
                for cluster in response['clusters']:
                    cluster_description = self.eks_client(region).describe_cluster(name=cluster)
                    if 'cluster' not in cluster_description or 'tags' not in cluster_description['cluster']:
                        self.log_err("Unexpected cluster description: {}", cluster_description)
                    elif 'pcw_ignore' not in cluster_description['cluster']['tags']:
                        clusters[region].append(cluster)
                if len(clusters[region]) == 0:
                    del clusters[region]
        return clusters

    @staticmethod
    def is_outdated(creation_time, valid_period_days) -> bool:
        return datetime.date(creation_time) < (date.today() - timedelta(days=valid_period_days))

    def cleanup_snapshots(self, valid_period_days):
        for region in self.all_regions:
            response = self.ec2_client(region).describe_snapshots(OwnerIds=['self'])
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

    def cleanup_volumes(self, valid_period_days):
        for region in self.all_regions:
            response = self.ec2_client(region).describe_volumes()
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

    def volume_protected(self, volume):
        if 'Tags' in volume:
            for tag in volume['Tags']:
                if tag['Key'] == 'pcw_ignore':
                    return True
        return False

    def list_instances(self, region):
        return list(self.ec2_resource(region).instances.all())

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

    def wait_for_empty_nodegroup_list(self, region, cluster_name, timeout_minutes=20):
        if self.dry_run:
            self.log_info("Skip waiting due to dry-run mode")
            return True
        self.log_info("Waiting empty nodegroup list in {}", cluster_name)
        end = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
        resp_nodegroup = self.eks_client(region).list_nodegroups(clusterName=cluster_name)

        while datetime.now(timezone.utc) < end and len(resp_nodegroup['nodegroups']) > 0:
            time.sleep(20)
            resp_nodegroup = self.eks_client(region).list_nodegroups(clusterName=cluster_name)
            if len(resp_nodegroup['nodegroups']) > 0:
                self.log_info("Still waiting for {} nodegroups to disappear", len(resp_nodegroup['nodegroups']))

    def delete_all_clusters(self):
        self.log_info("Deleting all clusters!")
        for region in self.cluster_regions:
            response = self.eks_client(region).list_clusters()
            if len(response['clusters']):
                self.log_info("Found {} cluster(s) in {}", len(response['clusters']), region)
                for cluster in response['clusters']:
                    resp_nodegroup = self.eks_client(region).list_nodegroups(clusterName=cluster)
                    if len(resp_nodegroup['nodegroups']):
                        self.log_info("Found {} nodegroups for {}", len(resp_nodegroup['nodegroups']), cluster)
                        for nodegroup in resp_nodegroup['nodegroups']:
                            if self.dry_run:
                                self.log_info("Skipping {} nodegroup deletion due to dry-run mode", nodegroup)
                            else:
                                self.log_info("Deleting {}", nodegroup)
                                self.eks_client(region).delete_nodegroup(
                                    clusterName=cluster, nodegroupName=nodegroup)
                        self.wait_for_empty_nodegroup_list(region, cluster)
                    if self.dry_run:
                        self.log_info("Skipping {} cluster deletion due to dry-run mode", cluster)
                    else:
                        self.log_info("Finally deleting {} cluster", cluster)
                        self.eks_client(region).delete_cluster(name=cluster)

    def cleanup_all(self):
        valid_period_days = PCWConfig.get_feature_property('cleanup', 'ec2-max-age-days', self._namespace)

        if valid_period_days > 0:
            self.cleanup_images(valid_period_days)
            self.cleanup_snapshots(valid_period_days)
            self.cleanup_volumes(valid_period_days)
        if PCWConfig.getBoolean('cleanup/vpc_cleanup', self._namespace):
            self.cleanup_uploader_vpcs()

    def delete_vpc(self, region, vpc, vpc_id):
        try:
            self.log_info('{} has no associated instances. Initializing cleanup of it', vpc)
            self.delete_internet_gw(vpc)
            self.delete_routing_tables(vpc)
            self.delete_vpc_endpoints(region, vpc_id)
            self.delete_security_groups(vpc)
            self.delete_vpc_peering_connections(region, vpc_id)
            self.delete_network_acls(vpc)
            self.delete_vpc_subnets(vpc)
            if self.dry_run:
                self.log_info('Deletion of VPC skipped due to dry_run mode')
            else:
                # finally, delete the vpc
                self.ec2_resource(region).meta.client.delete_vpc(VpcId=vpc_id)
        except Exception as ex:
            self.log_err("{} on VPC deletion. {}", type(ex).__name__, traceback.format_exc())
            send_mail('{} on VPC deletion in [{}]'.format(type(ex).__name__, self._namespace), traceback.format_exc())

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

    def delete_vpc_peering_connections(self, region, vpc_id):
        response = self.ec2_client(region).describe_vpc_peering_connections(
            Filters=[{'Name': 'requester-vpc-info.vpc-id', 'Values': [vpc_id]}])
        for vpcpeer in response['VpcPeeringConnections']:
            vpcpeer_connection = self.ec2_resource(region).VpcPeeringConnection(vpcpeer['VpcPeeringConnectionId'])
            if self.dry_run:
                self.log_info('Deletion of {} skipped due to dry_run mode', vpcpeer_connection)
            else:
                self.log_info('Deleting {}', vpcpeer_connection)
                vpcpeer_connection.delete()

    def delete_security_groups(self, vpc):
        for sgroup in vpc.security_groups.all():
            if sgroup.group_name != 'default':
                if self.dry_run:
                    self.log_info('Deletion of {} skipped due to dry_run mode', sgroup)
                else:
                    self.log_info('Deleting {}', sgroup)
                    sgroup.delete()

    def delete_vpc_endpoints(self, region, vpc_id):
        response = self.ec2_client(region).describe_vpc_endpoints(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        for end_point in response['VpcEndpoints']:
            if self.dry_run:
                self.log_info('Deletion of {} skipped due to dry_run mode', end_point)
            else:
                self.log_info('Deleting {}', end_point)
                self.ec2_client(region).delete_vpc_endpoints(VpcEndpointIds=[end_point['VpcEndpointId']])

    def delete_routing_tables(self, vpc):
        for rtable in vpc.route_tables.all():
            # we can not delete main RouteTable's , not main one don't have associations_attributes
            if len(rtable.associations_attribute) == 0:
                if self.dry_run:
                    self.log_info('{} will be not deleted due to dry_run mode', rtable)
                else:
                    self.log_info('Deleting {}', rtable)
                    rtable.delete()

    def delete_internet_gw(self, vpc):
        for gate in vpc.internet_gateways.all():
            if self.dry_run:
                self.log_info('{} will be not deleted due to dry_run mode', gate)
            else:
                self.log_info('Deleting {}', gate)
                vpc.detach_internet_gateway(InternetGatewayId=gate.id)
                gate.delete()

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
                        if len(list(subnet.instances.all())) > 0:
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

    def cleanup_images(self, valid_period_days):
        for region in self.all_regions:
            response = self.ec2_client(region).describe_images(Owners=['self'])
            for img in response['Images']:
                if EC2.is_outdated(parse(img['CreationDate']), valid_period_days):
                    if self.dry_run:
                        self.log_info("Image deletion {} skipped due to dry run mode", img['ImageId'])
                    else:
                        self.log_dbg("Delete image '{}' (ami:{})".format(img['Name'], img['ImageId']))
                        self.ec2_client(region).deregister_image(ImageId=img['ImageId'], DryRun=False)
