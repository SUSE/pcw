from django.db import models


class User(object):
    name = None
    id = None
    create_date = None
    keys = []

    def __init__(self, name=None, id=None, create_date=None, keys=None):
        self.name = name
        self.id = id
        self.create_date = create_date
        self.keys = keys
        if self.keys is None:
            self.keys = []


class AccessKey(object):
    key_id = None
    status = None
    create_date = None
    secret = None

    def __init__(self, key_id=None, status=None, create_date=None,
                 secret=None):
        self.key_id = key_id
        self.status = status.lower()
        self.create_date = create_date
        self.secret = secret


class Instance(models.Model):
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    active = models.BooleanField(default=False)
    instance_id = models.CharField(max_length=200, unique=True)
    region = models.CharField(max_length=64, default='')
    csp_info = models.TextField(default='')

    def age(self):
        return self.last_seen - self.first_seen
