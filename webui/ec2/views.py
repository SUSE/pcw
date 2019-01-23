from django.http import HttpResponseForbidden, HttpResponseServerError
from django.http import HttpResponseNotFound
from django.shortcuts import redirect
from rest_framework.response import Response
from ec2.serializers import UserSerializer, AccessKeySerializer
from rest_framework import views
from rest_framework.authentication import SessionAuthentication
from rest_framework.authentication import BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from . import EC2
from . import provider_conf
from . import EC2db
from ec2.models import Instance
from ec2.tables import InstanceTable
from ec2.tables import InstanceFilter
from django_tables2 import SingleTableView
import re
import time


class UserView (views.APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request, name=None):
        yourdata = EC2.get_users(name)
        results = UserSerializer(yourdata, many=True).data
        return Response(results)

    def delete(self, request, name):
        # Allow only tmp users to be deleted
        p = re.compile('^{}$'.format(
            provider_conf.EC2['username_pattern'].replace('{}', '\\d+')))
        if not p.match(name):
            return HttpResponseForbidden()

        if EC2.delete_user(name):
            return Response('OK')
        else:
            return HttpResponseNotFound()

    def post(self, request):
        name = provider_conf.EC2['username_pattern'].format(int(time.time()))
        yourdata = EC2.create_user(name)
        results = UserSerializer(yourdata).data
        return Response(results)


class AccessKeyView (views.APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request, key_id):
        key = EC2.get_key(key_id)
        if key:
            return Response(AccessKeySerializer(key).data)
        else:
            return HttpResponseNotFound()

    def delete(self, request, key_id):
        if EC2.delete_key(key_id):
            return Response('OK')
        else:
            return HttpResponseNotFound()

    def post(self, request):
        name = provider_conf.EC2['username_pattern'].format(int(time.time()))
        user = EC2.create_user(name)
        for key in user.keys:
            if key.secret is not None:
                return Response(AccessKeySerializer(key).data)
        return HttpResponseServerError()


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


class FilteredInstanceTableView(FilteredSingleTableView):
    model = Instance
    table_class = InstanceTable
    filter_class = InstanceFilter


def update(request):
    for region in EC2.list_regions():
        EC2db.sync_instances_db(region, EC2.list_instances(region=region))
    return redirect('instances')
