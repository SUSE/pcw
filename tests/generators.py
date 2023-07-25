import json
from faker import Faker
from datetime import datetime
from ocw.models import Instance, CspInfo

fake = Faker()
max_age_hours = 7
azure_storage_resourcegroup = 'openqa'
ec2_max_age_days = 1


def mock_get_feature_property(feature: str, property: str, namespace: str = None):
    if property == 'max-age-hours':
        return max_age_hours
    elif property == 'azure-storage-resourcegroup':
        return azure_storage_resourcegroup
    elif property == 'ec2-max-age-days':
        return ec2_max_age_days


def generate_model_instance(jobid_tag, created_by_tag):
    json_dump_tags = json.dumps({
        'openqa_var_job_id': jobid_tag,
        'openqa_created_by': created_by_tag
    })
    return Instance(
        cspinfo=CspInfo(tags=json_dump_tags, type=fake.uuid4()),
        provider=fake.uuid4(),
        instance_id=fake.uuid4(),
        vault_namespace=fake.uuid4()
    )


class ec2_csp_instance_mock:
    def __init__(self, tags_type):
        if tags_type == "random":
            tags = [{'Key': fake.uuid4(), 'Value': fake.uuid4()}]
        elif tags_type == "empty":
            tags = []
        self.instance_id = fake.uuid4()
        self.instance_type = fake.uuid4()
        self.launch_time = datetime.now()
        self.tags = tags


class azure_instance_mock:
    def __init__(self, tags_str):
        if tags_str == "openqa_created_date":
            self.tags = {"openqa_created_date": datetime.now().strftime("%c")}
        elif tags_str == "random":
            self.tags = {"key1": fake.uuid4()}
        elif tags_str == "no_tags":
            self.tags = {}
        self.name = fake.uuid4()
        self.location = fake.uuid4()


def gce_instance_mock(metadata_str):
    if metadata_str == "random_with_sshkey":
        metadata = {'items': [
            {'key': fake.uuid4(), 'value': fake.uuid4()},
            {'key': 'sshKeys', 'value': fake.uuid4()}
        ]}
    elif metadata_str == "empty_items":
        metadata = {'items': []}
    elif metadata_str == "creation_date_tag":
        metadata = {'items': [{'key': 'openqa_created_date', 'value': datetime.now().strftime("%c")}]}
    elif metadata_str == "empty_metadata":
        metadata = {}
    return {
        'id': fake.uuid4(),
        'machineType': fake.uuid4() + '/qq',
        'zone': fake.uuid4() + '/qq',
        'creationTimestamp': datetime.now(),
        'metadata': metadata
    }
