from ocw.lib.emailnotify import draw_instance_table
from tests.generators import generate_model_instance


def test_draw_instance_table():
    objects = [
            generate_model_instance(123, 'openqa-suse-de'),
            generate_model_instance(666, 'i-dont-have-a-link')
            ]
    s = draw_instance_table(objects)

    assert 'https://openqa.suse.de/t123' in s
    assert 'https://openqa.suse.de/t666' not in s

    for instance_id in [o.instance_id for o in objects]:
        assert instance_id in s
