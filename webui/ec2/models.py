
class User(object):
    name = None
    id = None
    create_date = None
    keys = []

    def __init__(self, name=None, id=None, create_date=None):
        self.name = name
        self.id = id
        self.create_date = create_date
        self.keys = []


class AccessKey(object):
    key_id = None
    status = None
    create_date = None
    secret = None

    def __init__(self, key_id=None, status=None, create_date=None):
        self.key_id = key_id
        self.status = status.lower()
        self.create_date = create_date
        self.secret = None
