FROM registry.opensuse.org/opensuse/leap:15.3

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UWSGI_WSGI_FILE=/pcw/webui/wsgi.py UWSGI_MASTER=1
ENV UWSGI_HTTP_AUTO_CHUNKED=1 UWSGI_HTTP_KEEPALIVE=1 UWSGI_LAZY_APPS=1 UWSGI_WSGI_ENV_BEHAVIOR=holy

## System preparation steps ################################################# ##

COPY . /pcw/

# We do the whole installation and configuration in one layer:
# * Install system requirements
RUN zypper -n ar http://download.suse.de/ibs/SUSE:/CA/openSUSE_Leap_15.3/ SUSE_CA && \
    zypper -n in ca-certificates-suse python3 python3-devel python3-pip gcc && rm -rf /var/cache
# Install pip requirements
RUN pip install -r /pcw/requirements.txt && rm -rf /var/cache

## Finalize ################################################################# ##

VOLUME /etc/pcw.ini
VOLUME /pcw/db

EXPOSE 8000/tcp

WORKDIR /pcw
# Once we are certain that this runs nicely, replace this with ENTRYPOINT.
CMD ["/pcw/container-startup", "run"]
