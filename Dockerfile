FROM registry.opensuse.org/opensuse/leap:15.3

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UWSGI_WSGI_FILE=/pcw/webui/wsgi.py UWSGI_MASTER=1
ENV UWSGI_HTTP_AUTO_CHUNKED=1 UWSGI_HTTP_KEEPALIVE=1 UWSGI_LAZY_APPS=1 UWSGI_WSGI_ENV_BEHAVIOR=holy

## System preparation steps ################################################# ##

COPY . /pcw/

# We do the whole installation and configuration in one layer:
# * Install system requirements
# * Install pip requirements
# * Empty system cache to conserve some space
RUN zypper -n in python3 python3-devel python3-pip gcc && pip3 install -r /pcw/requirements.txt && rm -rf /var/cache

## Finalize ################################################################# ##

VOLUME /pcw/db

EXPOSE 8000/tcp

WORKDIR /pcw
# Once we are certain that this runs nicely, replace this with ENTRYPOINT.
CMD ["/pcw/container-startup", "run"]
