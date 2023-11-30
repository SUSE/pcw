from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.core.serializers import serialize
from django.shortcuts import redirect
from django_tables2 import SingleTableView
from .lib import db
from .models import Instance
from .tables import InstanceTable
from .tables import InstanceFilter

# pylint: disable=unused-argument


class FilteredSingleTableView(SingleTableView):  # pylint: disable=too-many-ancestors
    filter_class = None
    filter = None

    def get_table_data(self):
        data = super().get_table_data()
        self.filter = self.filter_class(self.request.GET, queryset=data)
        return self.filter.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter'] = self.filter
        return context


# Displayed with '/ocw/instances' @see urls.py
class FilteredInstanceTableView(FilteredSingleTableView):  # pylint: disable=too-many-ancestors
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
            "namespace",
            "ignore"
        ),
    )
    return HttpResponse(data, content_type="application/json")


def update(request):
    db.start_update()
    return redirect('instances')


def update_status(request):
    return JsonResponse({
                'status': 'running' if db.is_updating() else 'idle',
                'last_update': db.last_update()
                })


@login_required
def delete(request, key_id=None):
    obj = Instance.objects.get(id=key_id)
    db.delete_instance(obj)
    return redirect('update')
