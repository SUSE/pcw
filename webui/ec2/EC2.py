from . import provider_conf
from .models import User, AccessKey
import boto3
from botocore.exceptions import ClientError


def _ec2user_to_user(ec2user):
    u = User()
    u.name = ec2user.get('UserName')
    u.id = ec2user.get('UserId')
    u.create_date = ec2user.get('CreateDate')
    u.keys = []
    return u


def _user_add_keys(user):
    iam = boto3.client('iam', aws_access_key_id=provider_conf.EC2['key'],
                       aws_secret_access_key=provider_conf.EC2['secret'])
    for response in iam.get_paginator('list_access_keys').paginate(
            UserName=user.name):
        for key in response.get('AccessKeyMetadata'):
            k = AccessKey()
            k.create_date = key.get('CreateDate')
            k.key_id = key.get('AccessKeyId')
            k.status = key.get('Status').lower()
            user.keys.append(k)
    return user


def get_users(name=None):
    '''
    See for more details on boto iam api.
        https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/iam.html
    '''
    iam = boto3.client('iam', aws_access_key_id=provider_conf.EC2['key'],
                       aws_secret_access_key=provider_conf.EC2['secret'])
    users = []
    if name:
        try:
            response = iam.get_user(UserName=name)
            user = response.get('User')
            u = _ec2user_to_user(user)
            _user_add_keys(u)
            users.append(u)
        except ClientError as ex:
            print(ex)
    else:
        for response in iam.get_paginator('list_users').paginate():
            for user in response.get('Users'):
                u = _ec2user_to_user(user)
                _user_add_keys(u)
                users.append(u)

    return users


def get_user_by_key(key_id):
    users = get_users()

    for user in users:
        for key in user.keys:
            if key_id == key.key_id:
                return user
    return None


def get_key(key_id):
    users = get_users()
    for user in users:
        for key in user.keys:
            if key_id == key.key_id:
                return key
    return None


def delete_key(key_id):
    user = get_user_by_key(key_id)
    if user is None:
        return False
    if len(user.keys) == 1:
        return delete_user(user.name)
    else:
        iam_res = boto3.resource(
            'iam', aws_access_key_id=provider_conf.EC2['key'],
            aws_secret_access_key=provider_conf.EC2['secret'])
        key = iam_res.AccessKey(user.name, key_id)
        key.delete()
        return True


def delete_user(username):
    iam = boto3.client('iam', aws_access_key_id=provider_conf.EC2['key'],
                       aws_secret_access_key=provider_conf.EC2['secret'])
    iam_res = boto3.resource('iam', aws_access_key_id=provider_conf.EC2['key'],
                             aws_secret_access_key=provider_conf.EC2['secret'])

    try:
        user = iam_res.User(username)
        user.load()

        for key in user.access_keys.all():
            key.delete()

        responses = iam.get_paginator('list_attached_user_policies').paginate(
            UserName=username)
        for response in responses:
            for policy in response.get('AttachedPolicies'):
                user.detach_policy(PolicyArn=policy.get('PolicyArn'))
        user.delete()
        return True
    except Exception as e:
        print("User delete fail with {}".format(e))
        return False


def create_user(username):
    iam_res = boto3.resource('iam', aws_access_key_id=provider_conf.EC2['key'],
                             aws_secret_access_key=provider_conf.EC2['secret'])
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

    u = User()
    u.name = user.user_name
    u.id = user.user_id
    u.create_date = user.create_date
    k = AccessKey()
    k.create_date = key.create_date
    k.key_id = key.id
    k.status = key.status.lower()
    k.secret = key.secret
    u.keys = [k]
    return u
