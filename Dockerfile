# Note: some of the required packages are not available for Leap (yet) and using pip is not possible within OBS
#FROM registry.opensuse.org/opensuse/tumbleweed
FROM opensuse/tumbleweed

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UWSGI_WSGI_FILE=/pcw/webui/wsgi.py UWSGI_MASTER=1
ENV UWSGI_HTTP_AUTO_CHUNKED=1 UWSGI_HTTP_KEEPALIVE=1 UWSGI_LAZY_APPS=1 UWSGI_WSGI_ENV_BEHAVIOR=holy

## System preparation steps ################################################# ##

# Install system requirements
RUN zypper ref && zypper -n in tar gzip python3 python3-devel gcc python3-boto3 python3-azure-mgmt python3-msrestazure uwsgi uwsgi-python3 python3-requests python3-Django python3-django-filter python3-texttable python3-oauth2client python3-google-api-python-client python3-google-cloud-storage python3-python-dateutil python3-APScheduler python3-django-tables2 python3-django-bootstrap4 python3-azure-mgmt-storage python3-azure-storage-blob && rm -rf /var/cache

# Copy program files
COPY ocw  /pcw/ocw/
COPY webui  /pcw/webui/
COPY container-startup manage.py /pcw/

# WORKAROUND to account for the missing tzdata. Remove whenever you can, this is a dark magic hack.
COPY tzdata.tar /root
RUN tar -C /usr/lib/python3.8/site-packages/ -xf /root/tzdata.tar && rm /root/tzdata.tar

WORKDIR /pcw

# Run basic system check to ensure a healthy container
RUN ["/pcw/container-startup", "check"]


## Finalize ################################################################# ##

VOLUME /pcw/db

EXPOSE 8000/tcp

WORKDIR /pcw

# Once we are certain that this runs nicely, replace this with ENTRYPOINT.
CMD ["/pcw/container-startup", "run"]
