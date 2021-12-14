[![Build Status](https://travis-ci.com/SUSE/pcw.svg?branch=master)](https://travis-ci.com/SUSE/pcw)
[![codecov](https://codecov.io/gh/SUSE/pcw/branch/master/graph/badge.svg)](https://codecov.io/gh/SUSE/pcw)

# OpenQA Public cloud Helper

A web app which monitors, displays and deletes CSPs and linked resources. It tries to identify
left over instances and also performs some cleanup task. For instance it deletes old custom
uploaded images. Behavior differs per CSP.

## Installation

```
virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
```

## Requirements

 [Listed in requirements.txt](requirements.txt)


## Run django webui

First copy the [pwc.ini](templates/pwc.ini) to _/etc_

```
cp templates/pwc.ini /etc/pwc.ini
```

Open and edit _vault[user]_ and _vault[password]_. Those are required.
Add _notify[to]_ and _notify.namespace.qac[to]_ in case you want to receive notifications.

```
virtualenv env
source env/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser --email admin@example.com --username admin
python manage.py collectstatic
python manage.py runserver
```
=> http://127.0.0.1:8000/

## Codecov

Running codecov locally require installation of `pytest pytest-cov codecov`.
Then you can run it with
```
BROWSER=$(xdg-settings get default-web-browser)
pytest -v --cov=./ --cov-report=html && $BROWSER htmlcov/index.html
```
and explore the results in your browser

## Debug

To simplify problem investigation pcw has two [django commands](https://docs.djangoproject.com/en/3.1/howto/custom-management-commands/) :

[cleanup](ocw/management/commands/cleanup.py)

[updaterun](ocw/management/commands/updaterun.py)

this allows triggering core functionality without web UI. It is highly recommended to use `dry_run = True` in `pcw.ini` in
such cases.


