from webui.settings import ConfigFile
from ..models import Instance
from datetime import timedelta
from texttable import Texttable
from django.urls import reverse
from .. import views
import json
import smtplib


def send_mail(request):
    cfg = ConfigFile()
    if not cfg.has('notify'):
        return
    num_new = 0
    o = Instance.objects
    o = o.filter(active=True,
                 csp_info__icontains='openqa_created_by',
                 age__gt=timedelta(hours=int(cfg.get(['notify', 'age-hours'], 12))))

    table = Texttable(max_width=0)
    table.set_deco(Texttable.HEADER)
    table.header(['Provider', 'id', 'Created-By', 'Age', 'Delete'])
    for i in o:
        if i.notified is False:
            num_new += 1
        j = json.loads(i.csp_info)
        hours, remainder = divmod(i.age.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        table.add_row([
            i.provider,
            i.instance_id,
            j['tags']['openqa_created_by'],
            i.age_formated(),
            request.build_absolute_uri(reverse(views.delete, args=[i.id]))
            ])

    if num_new == 0:
        return

    smtp_server = cfg.get(['notify', 'smtp'])
    port = cfg.get(['notify', 'smtp-port'], 25)
    sender_email = cfg.get(['notify', 'from'])
    receiver_email = cfg.get(['notify', 'to'])
    subject = cfg.get(['notify', 'subject'], '[Openqa-Cloud-Watch] CSP left overs')
    message = '''\
Subject: {subject}
From: {_from}
To: {_to}


{table}
'''.format(subject=subject, _from=sender_email, _to=receiver_email, table=table.draw())
    print('Send notify email to {}'.format(receiver_email))
    server = smtplib.SMTP(smtp_server, port)
    server.ehlo()
    server.sendmail(sender_email, receiver_email, message)
    o.update(notified=True)
