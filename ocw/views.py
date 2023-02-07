from django.shortcuts import redirect
from django_tables2 import SingleTableView
from .lib import db
from .models import Instance
from .tables import InstanceTable
from .tables import InstanceFilter
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.core.serializers import serialize


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


def health(request):
    return JsonResponse({"status": "ok"})


def instance_json(request):
    instances = Instance.objects.filter(active=True)
    data = serialize(
        "json",
        instances,
        fields=(
            "provider",
            "state",
            "first_seen",
            "last_seen",
            "age",
            "ttl",
            "instance_id",
            "region",
            "vault_namespace"
        ),
    )
    return HttpResponse(data, content_type="application/json")


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


@login_required
def delete(request, key_id=None):
    o = Instance.objects.get(id=key_id)
    db.delete_instance(o)
    return redirect('update')
