FROM ghcr.io/suse/pcw_base_main:master

# Copy program files only
COPY ocw  /pcw/ocw/
COPY webui  /pcw/webui/
COPY containers/container-startup manage.py LICENSE /pcw/

WORKDIR /pcw

# Run basic system check to ensure a healthy container
RUN ["/pcw/container-startup", "check"]

## Finalize ################################################################# ##

VOLUME /pcw/db

EXPOSE 8000/tcp

# Required to use system certs in python-requests
ENV REQUESTS_CA_BUNDLE=/etc/ssl/ca-bundle.pem
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UWSGI_WSGI_FILE=/pcw/webui/wsgi.py UWSGI_MASTER=1
ENV UWSGI_HTTP_AUTO_CHUNKED=1 UWSGI_HTTP_KEEPALIVE=1 UWSGI_LAZY_APPS=1 UWSGI_WSGI_ENV_BEHAVIOR=holy

# Once we are certain that this runs nicely, replace this with ENTRYPOINT.
ENTRYPOINT ["/pcw/container-startup", "run"]
