from ocw.lib.emailnotify import draw_instance_table
from ocw.lib.db import ec2_to_local_instance
from ocw.models import Instance
from tests.generators import ec2_instance_mock


def test_draw_instance_table():
    objects = [
            ec2_to_local_instance(ec2_instance_mock(tags=
                {
                    'openqa_var_JOB_ID': 123,
                    'openqa_created_by': 'openqa-suse-de'
                }), 'ns', 'moon-west'),
                ec2_to_local_instance(ec2_instance_mock(tags=
                {
                    'openqa_var_JOB_ID': 666,
                    'openqa_created_by': 'i-dont-have-a-link'
                }), 'ns', 'moon-west')
            ]
    s = draw_instance_table(objects)

    assert 'https://openqa.suse.de/t123' in s
    assert 'https://openqa.suse.de/t666' not in s

    for instance_id in [o.instance_id for o in objects]:
        assert instance_id in s
