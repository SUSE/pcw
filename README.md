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
namespaces = VAULT_NAMESPACE, VAULT_NAMESPACE_2, ...
# Use this option only during development! When enabled last response from
# vault is stored in a file 'auth.json'. The file is located in '/tmp/pcw'
use-file-cache = False

[vault.namespace.XXX]
# XXX is the name of a namespace given in vault.namespaces
# provider should be ec2, azure or gcp
providers = csp1[, csp2]...

[ec2]
regions = eu-north-1, ap-south-1, eu-west-3, ...

# Add this section to enable email notification for left overs
[notify]
smtp = YOUR_EMAIL_RELAY
smtp-port = PORT_NUMER
to = RECEIPE_ADDRESS1[, RECEIPE_ADDRESS2]
from = FROM_ADDRESS
age-hours = NUMBER_OF_HOURS_TO_COUNT_AS_LEFT_OVER

[notify.namespace.XXX]
# Optional section to set a specific receiver of left over notifications for
# a defined vault namespace. XXX should be replaced with the vault namespace
to = RECEIPE_ADDRESS_NS_1[, RECEIPE_ADDRESS_NS_2]


[cleanup]
# Specifiy how many images per flavor get keept
max-images-per-flavor = 1
# Max age of an image file
max-images-age-hours = 744

[cleanup.namespace.XXX]
azure-storage-resourcegroup=openqa-upload
azure-storage-account-name=openqa

EOT

python manage.py migrate
python manage.py createsuperuser --email admin@example.com --username admin
python manage.py collectstatic
python manage.py runserver
```
=> http://127.0.0.1:8000/


