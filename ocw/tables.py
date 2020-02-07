# tutorial/tables.py
import django_tables2 as tables
import django_filters
from .models import Instance
from .models import ProviderChoice
from .models import StateChoice
from django_tables2.utils import A


class InstanceTable(tables.Table):
    opt = tables.LinkColumn('delete_instance', args=[A('pk')], text='delete')
    age = tables.Column(attrs={
        'td': {
            'class': lambda record: 'old' if record.age.seconds > 60*60 else ''
        }
    })

    def render_age(self, record):
        return record.age_formated()

    def render_ttl(self, record):
        return record.ttl_formated()

    class Meta:
        model = Instance
        exclude = ['active']
        template_name = 'django_tables2/bootstrap.html'
        row_attrs = {
                'class': lambda record: "state_{}".format(record.state)
                }


# Create a BaseFilterSet to support initial value
class BaseFilterSet(django_filters.FilterSet):
    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            data = data.copy()
            for name, f in self.base_filters.items():
                initial = f.extra.get('initial')
                if not data.get(name) and initial is not None:
                    if isinstance(initial, list):
                        data.setlistdefault(name, initial)
                    else:
                        data.setdefault(name, initial)
        super(BaseFilterSet, self).__init__(data, *args, **kwargs)


class InstanceFilter(BaseFilterSet):
    provider = django_filters.ChoiceFilter(field_name='provider', choices=ProviderChoice.choices())
    state = django_filters.MultipleChoiceFilter(field_name='state', choices=StateChoice.choices(),
                                                initial=[str(i) for i in [StateChoice.ACTIVE, StateChoice.DELETING]])
    region = django_filters.CharFilter(lookup_expr='icontains')
    instance_id = django_filters.CharFilter(lookup_expr='icontains', field_name='instance_id')
    csp_info = django_filters.CharFilter(lookup_expr='icontains', field_name='csp_info', initial='openqa_created_by')

    class Meta:
        model = Instance
        fields = ['provider', 'state', 'instance_id', 'region', 'csp_info']
