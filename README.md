# Public cloud Helper

This script should help with my common tasks for CSP (Cloud service Providers).

Currently only AWS is supported. In future I will extend it with Azure and GCE.


## Installation

```
virtualenv venv
. venv/bin/activate
pip install --editable .
```

## Requirements

* python3-virtualenv
* Click
* boto3
* django
* djangorestframework

## Run django webui

```
virtualenv env
source env/bin/activate

cd webui
$EDITOR credentials/provider_conf.py
python manage.py migrate
python manage.py createsuperuser --email admin@example.com --username admin
python manage.py runserver
```
=> http://127.0.0.1:8000/credentials/users


