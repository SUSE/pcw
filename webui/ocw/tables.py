# tutorial/tables.py
import django_tables2 as tables
import django_filters
from .models import Instance
from .models import ProviderChoice
from django.utils.html import format_html
from django_tables2.utils import A


class InstanceTable(tables.Table):
    opt = tables.LinkColumn('delete_instance', args=[A('pk')], text='delete')

    def render_age(self, value):
        color = 'red' if (value.seconds > 60 * 60) else 'green'
        return format_html('<span style="color:{}">{}</span>', color, value)

    class Meta:
        model = Instance
        template_name = 'django_tables2/bootstrap.html'


# Create a BaseFilterSet to support initial value
class BaseFilterSet(django_filters.FilterSet):
    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            data = data.copy()
            for name, f in self.base_filters.items():
                initial = f.extra.get('initial')
                if not data.get(name) and initial is not None:
                    data[name] = initial
        super(BaseFilterSet, self).__init__(data, *args, **kwargs)


class InstanceFilter(BaseFilterSet):
    provider = django_filters.ChoiceFilter(field_name='provider', choices=[(tag, tag.value) for tag in ProviderChoice])
    active = django_filters.BooleanFilter(field_name='active', initial=True)
    region = django_filters.CharFilter(lookup_expr='icontains')
    instance_id = django_filters.CharFilter(lookup_expr='icontains', field_name='instance_id')

    class Meta:
        model = Instance
        fields = ['active', 'instance_id', 'region']
