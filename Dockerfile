FROM registry.suse.com/bci/python:3.11

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UWSGI_WSGI_FILE=/pcw/webui/wsgi.py UWSGI_MASTER=1
ENV UWSGI_HTTP_AUTO_CHUNKED=1 UWSGI_HTTP_KEEPALIVE=1 UWSGI_LAZY_APPS=1 UWSGI_WSGI_ENV_BEHAVIOR=holy

## System preparation steps ################################################# ##

# We do the whole installation and configuration in one layer:
COPY requirements.txt /pcw/
# * Install system requirements
# * Install pip requirements
# * Empty system cache to conserve some space
RUN source /etc/os-release && zypper addrepo -G -cf "https://download.opensuse.org/repositories/SUSE:/CA/$VERSION_ID/SUSE:CA.repo" && \
    zypper -n in ca-certificates-suse gcc libffi-devel && pip install --no-cache-dir -r /pcw/requirements.txt && zypper clean && rm -rf /var/cache

# Copy program files only
COPY ocw  /pcw/ocw/
COPY webui  /pcw/webui/
COPY container-startup manage.py LICENSE README.md setup.cfg pyproject.toml /pcw/

WORKDIR /pcw

# Run basic system check to ensure a healthy container
RUN ["/pcw/container-startup", "check"]

## Finalize ################################################################# ##

VOLUME /pcw/db

EXPOSE 8000/tcp

# Required to use system certs in python-requests
ENV REQUESTS_CA_BUNDLE=/etc/ssl/ca-bundle.pem

# Once we are certain that this runs nicely, replace this with ENTRYPOINT.
ENTRYPOINT ["/pcw/container-startup", "run"]
