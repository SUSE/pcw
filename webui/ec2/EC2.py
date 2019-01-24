from .models import User, AccessKey
import boto3
from botocore.exceptions import ClientError
from webui.settings import ConfigFile


class EC2:
    __instance = None
    __key = None
    __secret = None
    __iam_client = None
    __iam_resource = None
    __ec2_resource = dict()
    __ec2_client = dict()

    def __new__(cls):
        if EC2.__instance is None:
            EC2.__instance = object.__new__(cls)

        EC2.__instance.__secret = ConfigFile().get(['ec2', 'secret'], 'NaN')
        EC2.__instance.__key = ConfigFile().get(['ec2', 'key'], 'NaN')
        return EC2.__instance

    def iam_client(self):
        if self.__iam_client is None:
            self.__iam_client = boto3.client('iam', aws_access_key_id=self.__key, aws_secret_access_key=self.__secret)
        return self.__iam_client

    def iam_resource(self):
        if self.__iam_resource is None:
            self.__iam_resource = boto3.resource('iam', aws_access_key_id=self.__key,
                                                 aws_secret_access_key=self.__secret)
        return self.__iam_resource

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

    def _ec2user_to_user(self, ec2user):
        return User(ec2user.get('UserName'), ec2user.get('UserId'), ec2user.get('UserId'))

    def _user_add_keys(self, user):
        for response in self.iam_client().get_paginator('list_access_keys').paginate(
                UserName=user.name):
            for key in response.get('AccessKeyMetadata'):
                user.keys.append(AccessKey(key.get('AccessKeyId'), key.get(
                    'Status'), key.get('CreateDate')))
        return user

    def get_users(self, name=None):
        '''
        See for more details on boto iam api.
            https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/iam.html
        '''
        iam = self.iam_client()
        users = []
        if name:
            try:
                response = iam.get_user(UserName=name)
                user = response.get('User')
                u = self._ec2user_to_user(user)
                self._user_add_keys(u)
                users.append(u)
            except ClientError as ex:
                print(ex)
        else:
            for response in iam.get_paginator('list_users').paginate():
                for user in response.get('Users'):
                    u = self._ec2user_to_user(user)
                    self._user_add_keys(u)
                    users.append(u)

        return users

    def get_user_by_key(self, key_id):
        users = self.get_users()

        for user in users:
            for key in user.keys:
                if key_id == key.key_id:
                    return user
        return None

    def get_key(self, key_id):
        users = self.get_users()
        for user in users:
            for key in user.keys:
                if key_id == key.key_id:
                    return key
        return None

    def delete_key(self, key_id):
        user = self.get_user_by_key(key_id)
        if user is None:
            return False
        if len(user.keys) == 1:
            return self.delete_user(user.name)
        else:
            key = self.iam_resource().AccessKey(user.name, key_id)
            key.delete()
            return True

    def delete_user(self, username):
        try:
            user = self.iam_resource().User(username)
            user.load()

            for key in user.access_keys.all():
                key.delete()

            responses = self.iam_client().get_paginator('list_attached_user_policies').paginate(UserName=username)
            for response in responses:
                for policy in response.get('AttachedPolicies'):
                    user.detach_policy(PolicyArn=policy.get('PolicyArn'))
            user.delete()
            return True
        except Exception as e:
            print("User delete fail with {}".format(e))
            return False

    def create_user(self, username):
        iam_res = self.iam_resource()
        user = iam_res.User(username)
        try:
            user.load()
        except iam_res.meta.client.exceptions.NoSuchEntityException:
            try:
                user.create(Path="/pcw/auto-generated/")
            except ClientError:
                return None

            user.attach_policy(
                  PolicyArn='arn:aws:iam::aws:policy/AmazonEC2FullAccess'
            )

        try:
            key = user.create_access_key_pair()
        except ClientError:
            return None

        u = User(user.user_name, user.user_id, user.create_date,
                 [AccessKey(key.id, key.status, key.create_date, key.secret)])
        return u

    def list_instances(self, region='eu-central-1'):
        return self.ec2_resource(region).instances.all()

    def list_regions(self):
        regions_resp = self.ec2_client().describe_regions()
        regions = [region['RegionName'] for region in regions_resp['Regions']]
        return regions
