from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.http import HttpResponse
from django_tables2 import SingleTableView
from .lib.azure import Azure
from .lib.EC2 import EC2
from .lib.gce import GCE
from .lib import db
from .lib import emailnotify
from .models import Instance
from .models import ProviderChoice
from .models import StateChoice
from .tables import InstanceTable
from .tables import InstanceFilter
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse


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
    db.start_update()
    return redirect('instances')


def update_status(request):
    if 'application/json' in request.META.get('HTTP_ACCEPT'):
        return JsonResponse({
                  'status': 'running' if db.is_updating() else 'idle',
                  'last_update': db.last_update()
                  })

    return redirect('instances')


def cron(request):
    update(request)
    emailnotify.send_leftover_notification(request)
    return HttpResponse('Done...')


@login_required
def delete(request, key_id=None):
    o = Instance.objects.get(id=key_id)
    if 'openqa_created_by' not in o.csp_info:
        return HttpResponseForbidden('This instance isn\'t managed by openqa')

    if (o.provider == ProviderChoice.AZURE):
        Azure().delete_resource(o.instance_id)
    elif (o.provider == ProviderChoice.EC2):
        EC2().delete_instance(o.instance_id)
    elif (o.provider == ProviderChoice.GCE):
        GCE().delete_instance(o.instance_id, o.region)
    else:
        raise NotImplementedError(
                "Provider({}).delete() isn't implementd".format(o.provider))

    o.state = StateChoice.DELETING
    o.save()
    return redirect('update')
