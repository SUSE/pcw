from rest_framework import serializers


class AccessKeySerializer(serializers.Serializer):
    key_id = serializers.CharField(max_length=128)
    status = serializers.CharField(max_length=128)
    secret = serializers.CharField(max_length=128)
    create_date = serializers.DateTimeField()


class UserSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=32)
    id = serializers.CharField(max_length=128)
    create_date = serializers.DateTimeField()
    keys = AccessKeySerializer(many=True)
