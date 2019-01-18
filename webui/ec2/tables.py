# tutorial/tables.py
import django_tables2 as tables
import django_filters
from .models import Instance


class InstanceTable(tables.Table):
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
    active = django_filters.BooleanFilter(field_name='active', initial=True)
    region = django_filters.CharFilter(lookup_expr='icontains')
    instance_id = django_filters.CharFilter(lookup_expr='icontains', field_name='instance_id')

    class Meta:
        model = Instance
        fields = ['active', 'instance_id', 'region']
