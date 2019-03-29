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
* boto3
* azure
* django
* django-tables2
* django-filter
* django-bootstrap3


## Run django webui

```
virtualenv env
source env/bin/activate

cd webui

cat > /etc/pcw.ini << EOT
[vault]
url = https://publiccloud.your.vault.server/vault
user = Your_VAULT_USER
password = VAULT_USER_PASSWORD

# Add this section to enable email notification for left overs
[notify]
smtp = YOUR_EMAIL_RELAY
smtp-port = PORT_NUMER
to = RECEIPE_ADDRESS1[, RECEIPE_ADDRESS2]
from = FROM_ADDRESS
age-hours = NUMBER_OF_HOURS_TO_COUNT_AS_LEFT_OVER
EOT

python manage.py migrate
python manage.py createsuperuser --email admin@example.com --username admin
python manage.py runserver
```
=> http://127.0.0.1:8000/


