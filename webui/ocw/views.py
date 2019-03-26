from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django_tables2 import SingleTableView
from .lib.azure import Azure
from .lib.EC2 import EC2
from .lib import EC2db
from .lib import azure
from .models import Instance
from .models import ProviderChoice
from .tables import InstanceTable
from .tables import InstanceFilter
from django.contrib.auth.decorators import login_required


class FilteredSingleTableView(SingleTableView):
    filter_class = None

    def get_table_data(self):
        data = super(FilteredSingleTableView, self).get_table_data()
        self.filter = self.filter_class(self.request.GET, queryset=data)
        return self.filter.qs

    def get_context_data(self, **kwargs):
        context = super(FilteredSingleTableView, self).get_context_data(**kwargs)
        context['filter'] = self.filter
        return context


# Displayed with '/ocw/instances' @see urls.py
class FilteredInstanceTableView(FilteredSingleTableView):
    model = Instance
    table_class = InstanceTable
    filter_class = InstanceFilter


def update(request):
    azure.sync_instances_db(Azure().list_resource_groups())
    for region in EC2().list_regions():
        EC2db.sync_instances_db(region, EC2().list_instances(region=region))
    return redirect('instances')


@login_required
def delete(request, key_id=None):
    o = Instance.objects.get(id=key_id)
    if 'openqa_created_by' not in o.csp_info:
        return HttpResponseForbidden('This instance isn\'t managed by openqa')

    if (o.provider == str(ProviderChoice.AZURE)):
        Azure().delete_resource(o.instance_id)
    elif (o.provider == str(ProviderChoice.EC2)):
        EC2().delete_instance(o.instance_id)
    else:
        raise NotImplementedError(
                "Provider({}).delete() isn't implementd".format(o.provider))

    return redirect('update')
