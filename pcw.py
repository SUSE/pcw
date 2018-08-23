import click
import boto3
import datetime
import sys
from botocore.exceptions import ClientError


def displ_age(datetime_):
    now = datetime.datetime.now(datetime.timezone.utc)
    return ':'.join(str(now - datetime_).split(":")[:2])


@click.group()
@click.option('--access-key', envvar="ACCESS_KEY", prompt=True)
@click.option('--secret-key', envvar="SECRET_KEY", prompt=True)
@click.pass_context
def cli(ctx, access_key, secret_key):
    """Small collection of usefull aws commands """
    ctx.obj = {}
    ctx.obj['access_key'] = access_key
    ctx.obj['secret_key'] = secret_key


@cli.command('delete-user')
@click.argument('username')
@click.pass_context
def delete_user(ctx, username):
    """Delete the given user with all its dependencies"""

    iam_res = boto3.resource('iam', aws_access_key_id=ctx.obj['access_key'],
                             aws_secret_access_key=ctx.obj['secret_key'])

    user = iam_res.User(username)
    try:
        user.load()
    except ClientError as ex:
        print(ex)
        sys.exit(2)

    for key in user.access_keys.all():
        key.delete()

    for policy in user.attached_policies.all():
        policy.detach_user(UserName=username)

    user.delete()


@cli.command('list-users')
@click.pass_context
def list_users(ctx):
    """List all users"""

    iam = boto3.client('iam', aws_access_key_id=ctx.obj['access_key'],
                       aws_secret_access_key=ctx.obj['secret_key'])

    now = datetime.datetime.now(datetime.timezone.utc)
    print("{0:20}|{1:15}|{2:10}|{3}".format("Name", "Age", "Groups", "Keys"))
    for response in iam.get_paginator('list_users').paginate():
        for user in response.get('Users'):
            keys = "";
            for response in iam.get_paginator('list_access_keys').paginate(
                    UserName=user.get('UserName')):
                for key in response.get('AccessKeyMetadata'):
                    if (len(keys) > 0):
                        keys += ","
                    keys += key.get('AccessKeyId')
                    if (key.get('Status') == 'Inactive'):
                        keys += "(Inactive)"

            groups = iam.list_groups_for_user(UserName=user.get('UserName'))

            print("{0:20} {1:15} {2:10} {3}".format(user.get('UserName'),
                  displ_age(user.get('CreateDate')),
                  ",".join([g['GroupName'] for g in groups['Groups']]),
                  keys))


@cli.command('create-key')
@click.option('--username', default="auto-generated-user")
@click.option('--create-user', help="Create user, if not exists.", 
              is_flag=True, default=False)
@click.pass_context
def create_key(ctx, username, create_user):
    """Create a new access-key for the given user. If the user doesn't exists
    it will be created. Be aware of the maximum allowed number of access-keys
    per user, e.g. AWS allowes two per user."""

    iam = boto3.resource('iam',
                         aws_access_key_id=ctx.obj['access_key'],
                         aws_secret_access_key=ctx.obj['secret_key'])

    user = iam.User(username)
    try:
        user.load()
    except ClientError:
        print("User '{}' doesn't exists.".format(username))
        if not create_user:
            sys.exit(2)

        try:
            user.create(Path="/pcw/auto-generated/")
        except ClientError as err:
            print(err)
            sys.exit(2)

        user.attach_policy(
            PolicyArn='arn:aws:iam::aws:policy/AmazonEC2FullAccess'
        )

    try:
        key = user.create_access_key_pair()
    except ClientError as err:
        print(err)
        sys.exit(2)
    else:
        print("AWS_ACCESS_KEY_ID='{}'".format(key.id))
        print("AWS_SECRET_ACCESS_KEY='{}'".format(key.secret))


@cli.command('delete-key')
@click.argument('username')
@click.option('--keyid', default=None)
@click.option('--age', default=None)
@click.option('--dry', default=False, is_flag=True)
@click.pass_context
def delete_key(ctx, username, keyid, age, dry):
    """Delete access-keys from user."""

    iam_res = boto3.resource('iam', aws_access_key_id=ctx.obj['access_key'],
                             aws_secret_access_key=ctx.obj['secret_key'])
    user = iam_res.User(username)
    try:
        user.load()
    except ClientError as err:
        print(err)
        sys.exit(2)

    now = datetime.datetime.now(datetime.timezone.utc)

    for key in user.access_keys.all():
        if ((age and (now - key.create_date).total_seconds() >= int(age)) or
                (keyid and key.access_key_id == keyid)):
            if dry:
                print("[DRY RUN] Delete key {} from User {}".format(
                    key.access_key_id, username))
            else:
                key.delete()


@cli.command('list-instances')
@click.pass_context
def list_instances(ctx):
    """List all instances"""

    ec2 = boto3.resource('ec2', aws_access_key_id=ctx.obj['access_key'],
                         aws_secret_access_key=ctx.obj['secret_key'])

    print("{:20}|{:20}|{:10}|{:15}|{:15}".format("InstanceId", "AMI", "State",
                                                 "Type", "Age"))
    for i in ec2.instances.all():
        print("{:20} {:20} {:10} {:15} {:15} {:15}".format(
            i.instance_id, i.image_id, i.state['Name'], i.instance_type,
            displ_age(i.launch_time), i.public_dns_name))


@cli.command()
@click.option('--age', default=None)
@click.option('--instance-id', default=None)
@click.option('--dry', help="Do not terminate the instance, but display what "
              + "would be done.", default=False, is_flag=True)
@click.pass_context
def terminate(ctx, age, instance_id, dry):
    """Terminate instance(s). When specify a instances-id, the specific
    instance will be terminiated.
    When passing the paramter --age, all instances which running longer
    then the given time in seconds get terminated."""

    ec2 = boto3.resource('ec2', aws_access_key_id=ctx.obj['access_key'],
                         aws_secret_access_key=ctx.obj['secret_key'])
    if instance_id:
        i = ec2.Instance(instance_id)
        try:
            i.load()
        except ClientError as err:
            print(err)
            sys.exit(2)

        if dry:
            print("[DRY RUN] Terminate instance {}".format(selector))
        else:
            i.terminate()

    if age:
        age = int(age)
        instances = []
        now = datetime.datetime.now(datetime.timezone.utc)
        for i in ec2.instances.filter(
                Filters=[{'Name': 'instance-state-name',
                         'Values': ['running']}]):
            if (now - i.launch_time).total_seconds() >= age:
                if dry:
                    print("[DRY RUN] Terminate instance {} with age {}".format(
                        i.instance_id, displ_age(i.launch_time)))
                else:
                    i.terminate()
