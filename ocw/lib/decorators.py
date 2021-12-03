def filterService(*args, **kwargs):
    def wrapper(func):
        def filter_func(*args):
            return [email for email in func(*args) if email.startswith(kwargs['name'])]
        return filter_func
    return wrapper
