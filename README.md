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

```
virtualenv env
source env/bin/activate

cat > /etc/pcw.ini << EOT
[default]
# Your base url used to create links in email notifications. If it isn't
# present, the first entry of settings.ALLOWED_HOSTS is used.
base-url = https://publiccloud.qa.suse.de

# Fallback list when namespaces request for certain feature but not defined there
namespaces = VAULT_NAMESPACE, VAULT_NAMESPACE_2, ...

# Boolean value controlling wether pcw is running in "harmless" testing mode.
# if True pcw will not do any changes in target namespaces but just declare in log
# message what will be done. Default value is False
dry_run = [True,False]

[vault]
url = https://publiccloud.your.vault.server/vault
user = Your_VAULT_USER
password = VAULT_USER_PASSWORD
namespaces = VAULT_NAMESPACE, VAULT_NAMESPACE_2, ...

# Use this option only during development! When enabled last response from
# vault is stored in a file 'auth.json'. The file is located in '/tmp/pcw'
use-file-cache = False

providers = csp1[, csp2]...

# XYZ is the name of a namespace.
# Allows to overwrite settings specified in vault.
# Can be used for all properties except :
# - vault/url
# - vault/user
# - vault/password
# - vault/cert_dir
[vault.namespace.XYZ]
providers = csp1[, csp2]...

# Add this section to enable email notification for left overs
[notify]
smtp = YOUR_EMAIL_RELAY
smtp-port = PORT_NUMER
to = RECEIPE_ADDRESS1[, RECEIPE_ADDRESS2]
from = FROM_ADDRESS
age-hours = NUMBER_OF_HOURS_TO_COUNT_AS_LEFT_OVER

# XYZ is the name of a namespace.
# Allows to overwrite settings specified in notify.
# Can be used for all properties except :
# - notify/age-hours
# - notify/smtp
# - notify/smtp-port
# - notify/from
[notify.namespace.XYZ]
to = RECEIPE_ADDRESS_NS_1[, RECEIPE_ADDRESS_NS_2]


# while namespaces defined in vault section would be scanned for
# orphaned instances, this list of namespaces will be scanned for any
# other resources used in certain CSP. This behavior differs as much
# as architecture of every CSP differs
[cleanup]
# Specify with which namespace, we will do the cleanup.
# if not specifed default/namespaces list will be taken instead
namespaces = VAULT_NAMESPACE, VAULT_NAMESPACE_2, ...

# Specify how many images per flavor get kept
max-images-per-flavor = 1

# Max age of an image file
max-images-age-hours = 744

# special setting for EC2 controling maximal age of the snapshot
ec2-max-snapshot-age-days = 30

# XYZ is the name of a namespace.
# Allows to overwrite settings specified in cleanup.
[cleanup.namespace.XYZ]
azure-storage-resourcegroup=openqa-upload
azure-storage-account-name=openqa

#Scan and notify about orphaned EKS clusters ( AWS k8s )
[clusters]
namespaces = VAULT_NAMESPACE, VAULT_NAMESPACE_2, ...

EOT

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


