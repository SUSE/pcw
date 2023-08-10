[![codecov](https://codecov.io/gh/SUSE/pcw/branch/master/graph/badge.svg)](https://codecov.io/gh/SUSE/pcw)

# OpenQA Public cloud Helper

![PCW project logo](https://repository-images.githubusercontent.com/140823511/394bbeff-cd84-42f2-8a36-b4cd3923e4be)
> **Jose Lausuch**: Where you thinking about PCW while laying on the beach? :stuck_out_tongue:
> **Anton Smorodskyi**: YES, constantly! :partygeeko: I see it in every palm on the beach !

PublicCloud-Watcher (PCW) is a web app which monitors, displays and deletes resources on various Cloud Service Providers (CSPs).
PCW has two main flows :

1. **Update run ( implemented in [ocw/lib/db.py](ocw/lib/db.py) )** Executed every 5 minutes. Concentrates on deleting VMs (in case of Azure Resource Groups).
    - Each update run scans accounts defined in configuration file and
  writes the obtained results into a local sqlite database. Newly discovered entities get assigned an obligatory time-to-life value (TTL).
  TTL may be taken from tag `openqa_ttl` if entity is tagged with such tag if not PCW will check `pcw.ini` for `updaterun/default_ttl` setting
  and if setting is not defined than PCW will use hard-coded value from [webui/settings.py](webui/settings.py). Database has a web UI where
  you can manually trigger certain entity deletion.
    - After persisting results into db PCW deciding which entities needs to be deleted. There are two ways to survive for entity:
        a. Having tag `pcw_ignore` ( with any value)
        b. Age of entity is lower than TTL defined. Age is calculated as delta of last_seen and first_seen
    - For entities that survive cleanup PCW will sent notification email to the list defined in config.

2. **Cleanup ( implemented in [ocw/lib/cleanup.py](ocw/lib/cleanup.py) )** Executed every hour. Concentrates on everything except VM deletion. This vary a lot per CSP so let's clarify that on per provider level.
    - For Azure such entities monitored (check details in [ocw/lib/azure.py](ocw/lib/azure.py)):
        a. bootdiagnostics
        b. Blobs in `sle-images` container
        c. Disks assigned to certain resource groups
        d. Images assigned to certain resource groups
    - For EC2 such entities monitored (check details in [ocw/lib/ec2.py](ocw/lib/ec2.py)):
        a. Images in all regions defined
        b. Snapshots in all region defined
        c. Volumes in all regions defined
        d. VPC's ( deletion of VPC means deletion of all assigned to VPC entities first ( security groups , networks etc. ))
    - For GCE deleting disks, images & network resources (check details in [ocw/lib/gce.py](ocw/lib/gce.py))
    - For Openstack deleting instances, images & keypairs (check details in [ocw/lib/openstack.py](ocw/lib/openstack.py)


The fastest way to run PCW is via the provided containers, as described in the [Running a container](#running-a-container) section.

## Install

See the [requirements.txt](requirements.txt). It's recommended to setup `pcw` in a virtual environment to avoid package collisions:

```bash
virtualenv venv
. venv/bin/activate
pip install -r requirements.txt
```

## Configure and run

Configuration of PCW happens via a global config file in `/etc/pcw.ini`. See [templates/pcw.ini](templates/pcw.ini) for a configuration template. To start, copy the template over:

    cp templates/pwc.ini /etc/pcw.ini

To be able to connect to CSP PCW needs Service Principal details. Depending on namespaces defined in `pcw.ini`  PCW will expect some JSON files to be created
under `/var/pcw/[namespace name]/[Azure/EC2/GCE/Openstack].json`. See [templates/var/example_namespace/](templates/var/example_namespace/) for examples.

PCW supports email notifications about left-over instances. See the `notify` section therein and their corresponding comments.

```bash
# Setup virtual environment
virtualenv env
source env/bin/activate
pip install -r requirements.txt


## Configuration steps, only required once to setup the database and user
# Setup database
python manage.py migrate
# Setup superuser (OPTIONAL)
python manage.py createsuperuser --email admin@example.com --username admin
python manage.py collectstatic


## Running the webapp server
python manage.py runserver
```

By default, PCW runs on http://127.0.0.1:8000/

## Building a container

To build a docker/podman container with the default `suse/qac/pcw` tag, run

```bash
make docker-container
make podman-container
```

This repository contains the skeleton `Dockerfile` for building a PCW docker/podman container.

## Running a container

You can use the already build containers within [this repository](https://github.com/orgs/SUSE/packages?repo_name=pcw):

```bash
podman pull ghcr.io/suse/pcw:latest
```

The PCW container supports two volumes to be mounted:

* (required) `/etc/pcw.ini` - configuration ini file
* (optional) `/pcw/db` - volume where the database file is stored

To create a container using e.g. the data directory `/srv/pcw` for both volumes and expose port 8000, run the following:

```bash
podman create --hostname pcw --name pcw -v /srv/pcw/pcw.ini:/etc/pcw.ini -v /srv/pcw/db:/pcw/db -v <local creds storage>:/var/pcw -p 8000:8000/tcp ghcr.io/suse/pcw:latest
podman start pcw
```

For usage in docker simply replace `podman` by `docker` in the above command.

The `pcw` container runs by default the `/pcw/container-startup` startup helper script. You can interact with it by running

```bash
podman exec pcw /pcw/container-startup help

podman run -ti --rm --hostname pcw --name pcw -v /srv/pcw/pcw.ini:/etc/pcw.ini -v <local creds storage>:/var/pcw -v /srv/pcw/db:/pcw/db -p 8000:8000/tcp ghcr.io/suse/pcw:latest /pcw/container-startup help
```

To create an user within the created container named `pcw`, run

```bash
podman exec pcw /pcw/container-startup createuser admin USE_A_STRONG_PASSWORD
```

## Devel version of container

There is [devel version](Dockerfile_dev) of container file. Main difference is that source files are not copied into image but expected to be mounted via volume. This ease development in environment close as much as possible to production run.

Expected use would be :

```bash
make podman-container-devel
podman run  -v <local path to ini file>:/etc/pcw.ini -v <local creds storage>:/var/pcw -v <path to this folder>:/pcw  -t pcw-devel "python3 manage.py <any command available>"
```


## Codecov

Running codecov locally require installation of `pytest pytest-cov codecov`.
Then you can run it with

```bash
BROWSER=$(xdg-settings get default-web-browser)
pytest -v --cov=./ --cov-report=html && $BROWSER htmlcov/index.html
```

and explore the results in your browser

## Debug

To simplify problem investigation pcw has two [django commands](https://docs.djangoproject.com/en/3.1/howto/custom-management-commands/) :

[cleanup](ocw/management/commands/cleanup.py)

[updaterun](ocw/management/commands/updaterun.py)

those allows triggering core functionality without web UI. It is highly recommended to use `dry_run = True` in `pcw.ini` in
such cases.

## Testing

```bash
virtualenv ~/.pcw
source ~/.pcw/bin/activate
pip install -r requirements_test.txt
make test
```

The tests contain a Selenium test for the webUI that uses Podman.  Make sure that you have the latest [geckodriver](https://github.com/mozilla/geckodriver/releases) installed anywhere in your `PATH` and that the `podman.socket` is enabled:
`systemctl --user enable --now podman.socket`

Set the `SKIP_SELENIUM` environment variable when running `pytest` or `make test` to skip the Selenium test.
