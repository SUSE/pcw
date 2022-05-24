[![Build Status](https://travis-ci.com/SUSE/pcw.svg?branch=master)](https://travis-ci.com/SUSE/pcw)
[![codecov](https://codecov.io/gh/SUSE/pcw/branch/master/graph/badge.svg)](https://codecov.io/gh/SUSE/pcw)

# OpenQA Public cloud Helper

PublicCloud-Watcher or `pcw` is a web app which monitors, displays and deletes resources on various Cloud Service Providers (CSPs). It identifies abandoned instances by searching for certain tags and performs cleanup tasks. It also deletes old custom uploaded images. The behavior differs per CSP.

The fastest way to run PublicCloud-Watcher is via the provided containers, as described in the [Running a container](#running-a-container) section.

## Install

See the [requirements.txt](requirements.txt). It's recommended to setup `pcw` in a virtual environment to avoid package collisions:

    virtualenv venv
    . venv/bin/activate
    pip install -r requirements.txt

## Configure and run

Configuration of Publiccloud-Watcher happens via a global config file in `/etc/pcw.ini`. See [templates/pcw.ini](templates/pcw.ini) for a configuration template. To start, copy the template over:

    cp templates/pwc.ini /etc/pcw.ini

The bare minimum configuration requires the `vault[user]` and `vault[password]` settings.

PCW supports email notifications about left-over instances. See the `notify` section therein and their corresponding comments.

```bash
# Setup virtual environment
virtualenv env
source env/bin/activate
pip install -r requirements.txt


## Configuration steps, only required once to setup the database and user
# Setup database
python manage.py migrate
# Setup superuser
python manage.py createsuperuser --email admin@example.com --username admin
python manage.py collectstatic


## Running the webapp server
python manage.py runserver
```

By default, PCW runs on http://127.0.0.1:8000/

## Building a container

To build a docker/podman container with the default `suse/qac/pcw` tag, run

    make docker-container
    make podman-container

This repository contains the skeleton `Dockerfile` for building a Publiccloud-Watcher docker/podman container.

## Running a container

You can use the already build containers within [this repository](https://github.com/orgs/SUSE/packages?repo_name=pcw): 

    podman pull ghcr.io/suse/pcw:latest

The PublicCloud-Watcher container supports two volumes to be mounted:

* (required) `/etc/pcw.ini` - configuration ini file
* (optional) `/pcw/db` - volume where the database file is stored

To create a container using e.g. the data directory `/srv/pcw` for both volumes and expose port 8000, run the following:

    podman create --hostname pcw --name pcw -v /srv/pcw/pcw.ini:/etc/pcw.ini -v /srv/pcw/db:/pcw/db -p 8000:8000/tcp ghcr.io/suse/pcw:latest
    podman start pcw

For usage in docker simply replace `podman` by `docker` in the above command.

The `pcw` container runs by default the `/pcw/container-startup` startup helper script. You can interact with it by running

    podman exec pcw /pcw/container-startup help
    
    podman run -ti --rm --hostname pcw --name pcw -v /srv/pcw/pcw.ini:/etc/pcw.ini -v /srv/pcw/db:/pcw/db -p 8000:8000/tcp ghcr.io/suse/pcw:latest /pcw/container-startup help

To create the admin superuser within the created container named `pcw`, run

    podman run -ti --rm -v /srv/pcw/pcw.ini:/etc/pcw.ini -v /srv/pcw/db:/pcw/db -p 8000:8000/tcp ghcr.io/suse/pcw:latest /pcw/container-startup createsuperuser --email admin@example.com --username admin

## Codecov

Running codecov locally require installation of `pytest pytest-cov codecov`.
Then you can run it with

    BROWSER=$(xdg-settings get default-web-browser)
    pytest -v --cov=./ --cov-report=html && $BROWSER htmlcov/index.html

and explore the results in your browser

## Debug

To simplify problem investigation pcw has two [django commands](https://docs.djangoproject.com/en/3.1/howto/custom-management-commands/) :

[cleanup](ocw/management/commands/cleanup.py)

[updaterun](ocw/management/commands/updaterun.py)

those allows triggering core functionality without web UI. It is highly recommended to use `dry_run = True` in `pcw.ini` in
such cases.
