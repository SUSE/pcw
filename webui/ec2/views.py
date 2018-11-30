from django.http import HttpResponseForbidden
from rest_framework.response import Response
from ec2.serializers import UserSerializer
from rest_framework import viewsets
from rest_framework import views
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework.permissions import IsAuthenticated
from . import EC2
import re
import time

class UserView (views.APIView):
    authentication_classes = (SessionAuthentication, BasicAuthentication)
    permission_classes = (IsAuthenticated,)

    def get(self, request, name = None):
        yourdata = EC2.get_users(name)
        results = UserSerializer(yourdata, many=True).data
        return Response(results)

    def delete(self, request, name):
        # Allow only tmp users to be deleted
        p = re.compile('^tmp_\d+_openqa.suse.de$')
        if not p.match(name):
            return HttpResponseForbidden()

        EC2.delete_user(name)
        return Response("OK");

    def post(self, request):
        name = "tmp_{}_openqa.suse.de".format(int(time.time()));
        yourdata = EC2.create_user(name)
        results = UserSerializer(yourdata).data
        return Response(results)

