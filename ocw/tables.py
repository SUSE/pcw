# tutorial/tables.py
import django_tables2 as tables
import django_filters
from .models import Instance
from .models import ProviderChoice
from .models import StateChoice
from django_tables2.utils import A
from django.utils.html import format_html
from django.templatetags.static import static
from django.template.loader import get_template


class NoHeaderLinkColumn(tables.LinkColumn):
    def header(self):
        return ""


class OpenQALinkColumn(tables.Column):
    def __init__(self, *args, **kwargs):
        kwargs['accessor'] = 'pk'
        super().__init__(*args, **kwargs)

    def header(self):
        return ""

    def render(self, record):
        link = record.get_openqa_job_link()
        if link is not None:
            return format_html('<a href="{}" "><img alt="{}" title="{}" src="{}"/></a>',
                               link['url'], link['title'], link['title'], static('img/openqa.svg'))
        return ""


class MailColumn(tables.BooleanColumn):
    def header(self):
        return ""

    def render(self, value, record, bound_column):
        value = self._get_bool_value(record, value, bound_column)
        if value:
            return format_html('<img alt="Email notification was send" src="{}" width=20 height=20/>',
                               static('img/notified.png'))
        else:
            return ""


class CspInfoColumn(tables.TemplateColumn):

    def __init__(self, template_name=None, **extra):
        super().__init__(template_name="ocw/csp_info.html", orderable=False, **extra)

    @property
    def header(self, **kwargs):
        return get_template('ocw/csp_info_header.html').render()


class InstanceTable(tables.Table):
    csp_info = CspInfoColumn()
    notified = MailColumn()
    delete = NoHeaderLinkColumn('delete_instance', args=[A('pk')],
                                text=format_html('<img width=20 height=20 title="Delete instance" src="{}"/>',
                                                 static('img/trash.png'))
                                )
    openqa = OpenQALinkColumn()
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
    csp_info = django_filters.CharFilter(lookup_expr='icontains', field_name='csp_info')

    class Meta:
        model = Instance
        fields = ['provider', 'state', 'instance_id', 'region', 'csp_info']
