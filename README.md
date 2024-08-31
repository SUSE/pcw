[![codecov](https://codecov.io/gh/SUSE/pcw/branch/master/graph/badge.svg)](https://codecov.io/gh/SUSE/pcw)

# OpenQA Public cloud Helper

![PCW project logo](https://repository-images.githubusercontent.com/140823511/394bbeff-cd84-42f2-8a36-b4cd3923e4be)
> **Jose Lausuch**: Where you thinking about PCW while laying on the beach? :stuck_out_tongue:
> **Anton Smorodskyi**: YES, constantly! :partygeeko: I see it in every palm on the beach !

PublicCloud-Watcher (PCW) is a web app which monitors, displays and deletes resources on various Cloud Service Providers (CSPs).
PCW has three main flows :

1. **Update run ( implemented in [ocw/lib/db.py](ocw/lib/db.py) )** Executed every 45 minutes. Concentrates on deleting VMs (in case of Azure Resource Groups).
    - Each update scans accounts defined in configuration file and writes the obtained results into a local sqlite database. Newly discovered entities get assigned an obligatory time-to-life value (TTL). TTL may be taken from tag `openqa_ttl` if entity is tagged with such tag if not PCW will check `pcw.ini` for `updaterun/default_ttl` setting and if setting is not defined than PCW will use hard-coded value from [webui/settings.py](webui/settings.py). Database has a web UI where you can manually trigger certain entity deletion.
    - After persisting results into db PCW deciding which entities needs to be deleted. There are two ways to survive for entity:
        a. Having tag `pcw_ignore` ( with any value)
        b. Age of entity is lower than TTL defined. Age is calculated as delta of last_seen and first_seen
    - For entities that survive cleanup PCW will sent notification email to the list defined in config.

2. **Cleanup ( implemented in [ocw/lib/cleanup.py](ocw/lib/cleanup.py) )** Execution via django command. Concentrates on everything except VM deletion. This vary a lot per CSP so let's clarify that on per provider level.
    - For Azure such entities monitored (check details in [ocw/lib/azure.py](ocw/lib/azure.py)):
        a. bootdiagnostics
        b. Blobs in all containers
        c. Disks assigned to certain resource group defined in pcw.ini ('azure-storage-resourcegroup')
        d. Images assigned to certain resource group defined in pcw.ini ('azure-storage-resourcegroup')
        e. Image versions assigned to certain resource group defined in pcw.ini  ('azure-storage-resourcegroup')
    - For EC2 such entities monitored (check details in [ocw/lib/ec2.py](ocw/lib/ec2.py)):
        a. Images in all regions defined
        b. Snapshots in all region defined
        c. Volumes in all regions defined
        d. VPC's ( deletion of VPC means deletion of all assigned to VPC entities first ( security groups , networks etc. ))
    - For GCE deleting disks, images & network resources (check details in [ocw/lib/gce.py](ocw/lib/gce.py))
3. **Dump entities quantity ( implemented in [ocw/lib/dumpstate.py](ocw/lib/dumpstate.py) )**. To be able to react fast on possible bugs in PCW and/or unexpected creation of many resources there is ability to dump real time data from each CSP into defined InfluxDB instance. This allow building real-time dashboards and/or setup  notification flow.


The fastest way to run PCW is via the provided containers, as described in the [Running a container](#running-a-container) section.

# Usage

## Python virtualenv

### Requirements files

PCW has 3 sets of virtual env requirements files :
 - [requirements.txt](requirements.txt) common usage for everything except K8S related cleanups
 - [requirements_k8s.txt](requirements_k8s.txt) due to high volume of dependencies needed only in single use case (k8s cleanups) they excluded in independent category
 - [requirements_test.txt](requirements_test.txt) contains dependencies allowing to run pcw's unit tests

### Configuration
Configuration of PCW happens via a global config file in `/etc/pcw.ini`. See [templates/pcw.ini](templates/pcw.ini) for a configuration template. To start, copy the template over:

```bash
    cp templates/pwc.ini /etc/pcw.ini
```

### CSP credentials
To be able to connect to CSP PCW needs Service Principal details. Depending on namespaces defined in `pcw.ini`  PCW will expect some JSON files to be created
under `/var/pcw/[namespace name]/[Azure/EC2/GCE].json`. See [templates/var/example_namespace/](templates/var/example_namespace/) for examples.

PCW supports email notifications about left-over instances. See the `notify` section therein and their corresponding comments.

### Build and run

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

## PCW in container

### Available containers

In [containers](containers/) folder you main find several Dockerfiles to build several different images:

 - [Dockerfile](containers/Dockerfile) image based on [bci-python3.11](https://registry.suse.com/categories/bci-devel/repositories/bci-python311) and can be used to run all PCW functionality except k8s cleanup
 - [Dockerfile_k8s](containers/Dockerfile_k8s) image based on [bci-python3.11](https://registry.suse.com/categories/bci-devel/repositories/bci-python311) and can be used to run k8s cleanup
 - [Dockerfile_k8s_dev](containers/Dockerfile_k8s_dev) and [Dockerfile_dev](containers/Dockerfile_dev) images which contains same set of dependencies as [Dockerfile](containers/Dockerfile) and [Dockerfile_k8s](containers/Dockerfile_k8s) and expect PCW source code to be mounted as volumes. Very usefull for development experiments

### Execution

You can use the already build containers within [this repository](https://github.com/orgs/SUSE/packages?repo_name=pcw):

```bash
podman pull ghcr.io/suse/pcw_main:latest
podman pull ghcr.io/suse/pcw_k8s:latest
```

The PCW container supports two volumes to be mounted:

* (required) `/etc/pcw.ini` - configuration ini file
* (optional) `/pcw/db` - volume where the database file is stored

To create a container using e.g. the data directory `/srv/pcw` for both volumes and expose port 8000, run the following:

```bash
podman create --hostname pcw --name pcw -v /srv/pcw/pcw.ini:/etc/pcw.ini -v /srv/pcw/db:/pcw/db -v <local creds storage>:/var/pcw -p 8000:8000/tcp ghcr.io/suse/pcw_main:latest
podman start pcw
```

The `pcw` container runs by default the [/pcw/container-startup](containers/container-startup) startup helper script. You can interact with it by running

```bash
podman exec pcw /pcw/container-startup help

podman run -ti --rm --hostname pcw --name pcw -v /srv/pcw/pcw.ini:/etc/pcw.ini -v <local creds storage>:/var/pcw -v /srv/pcw/db:/pcw/db -p 8000:8000/tcp ghcr.io/suse/pcw_main:latest /pcw/container-startup help
```

To create an user within the created container named `pcw`, run

```bash
podman exec pcw /pcw/container-startup createuser admin USE_A_STRONG_PASSWORD
```

### Devel version

There is [devel version](containers/Dockerfile_dev) of container file. Main difference is that source files are not copied into image but expected to be mounted via volume. This ease development in environment close as much as possible to production run.

Expected use would be :

```bash
make container-devel
podman run  -v <local path to ini file>:/etc/pcw.ini -v <local creds storage>:/var/pcw -v <path to this folder>:/pcw  -t pcw-devel "python3 manage.py <any command available>"
```

## Test and debug

### Testing

```bash
virtualenv .
source bin/activate
pip install -r requirements_test.txt
make test
```

The tests contain a Selenium test for the webUI that uses Podman.  Make sure that you have the latest [geckodriver](https://github.com/mozilla/geckodriver/releases) installed anywhere in your `PATH` and that the `podman.socket` is enabled:
`systemctl --user enable --now podman.socket`

Set the `SKIP_SELENIUM` environment variable when running `pytest` or `make test` to skip the Selenium test.

### Debug

To simplify problem investigation pcw has several [django commands](https://docs.djangoproject.com/en/3.1/howto/custom-management-commands/) :

[cleanup](ocw/management/commands/cleanup.py)

[updaterun](ocw/management/commands/updaterun.py)

[dumpstate](ocw/management/commands/dumpstate.py)

[rmclusters](ocw/management/commands/rmclusters.py)

those allows triggering core functionality without web UI. It is highly recommended to use `dry_run = True` in `pcw.ini` in
such cases.
