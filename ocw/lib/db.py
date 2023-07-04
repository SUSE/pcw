import json
import traceback
import logging
from os.path import basename
from datetime import datetime, timedelta, timezone
import dateutil.parser as dateparser
from django.db import transaction
from django.db.models import F
from ocw.apps import getScheduler
from webui.PCWConfig import PCWConfig
from ..models import Instance, StateChoice, ProviderChoice, CspInfo
from .emailnotify import send_mail, send_leftover_notification
from .azure import Azure
from .ec2 import EC2
from .gce import GCE

logger = logging.getLogger(__name__)
RUNNING = False
LAST_UPDATE = None


@transaction.atomic
def save_or_update_instance(csp_data: dict) -> None:
    provider = csp_data['provider']
    namespace = csp_data['namespace']
    if Instance.objects.filter(provider=provider, instance_id=csp_data['id'], vault_namespace=namespace).exists():
        logger.debug("[%s] Update instance %s:%s", namespace, provider, csp_data['id'])
        local_instance = Instance.objects.get(provider=provider, instance_id=csp_data['id'], vault_namespace=namespace)
        if local_instance.region != csp_data['region']:
            logger.info("[%s] Instance %s:%s changed region from %s to %s", namespace,
                        provider, csp_data['id'], local_instance.region, csp_data['region'])
            local_instance.region = csp_data['region']
        if local_instance.state == StateChoice.DELETED:
            logger.info("[%s] %s:%s instance which still exists has DELETED state in DB.",
                        namespace, provider, csp_data['id'])
            local_instance.first_seen = csp_data['first_seen']
        local_instance.cspinfo.tags = json.dumps(csp_data['tags'])
    else:
        logger.debug("[%s] Create instance %s:%s", namespace, provider, csp_data['id'])
        local_instance = Instance(
            provider=provider,
            vault_namespace=namespace,
            first_seen=csp_data['first_seen'],
            instance_id=csp_data['id'],
            ttl=timedelta(seconds=int(csp_data['tags'].get('openqa_ttl', csp_data['default_ttl']))),
            region=csp_data['region']
        )
        CspInfo(tags=json.dumps(csp_data['tags']), type=csp_data['type'], instance=local_instance)
    # Azure has exceptional case when it is querying entity second time
    # because it is only way to get VM type(s) which is running inside resource group
    # it might happen that in such case we discovering that resource group already deleted
    # which means that set_alive() must be skipped
    if provider == ProviderChoice.AZURE and local_instance.cspinfo.type is None:
        logger.debug("[%s] Azure group %s already deleted", namespace, local_instance.instance_id)
    else:
        local_instance.set_alive()
        local_instance.save()
        local_instance.cspinfo.save()


def ec2_extract_data(csp_instance, namespace: str, region: str, default_ttl: int) -> dict:
    return {
        'tags': {t['Key']: t['Value'] for t in csp_instance.tags} if csp_instance.tags else {},
        'id': csp_instance.instance_id,
        'first_seen': dateparser.parse(csp_instance.launch_time.isoformat()),
        'namespace': namespace,
        'region': region,
        'provider': ProviderChoice.EC2,
        'type': csp_instance.instance_type,
        'default_ttl': default_ttl
    }


def azure_extract_data(csp_instance, namespace: str, default_ttl: int) -> dict:
    if csp_instance.tags:
        tags = csp_instance.tags
        first_seen = dateparser.parse(tags.get('openqa_created_date', str(datetime.now(tz=timezone.utc))))
    else:
        tags = {}
        first_seen = dateparser.parse(str(datetime.now(tz=timezone.utc)))
    return {
        'tags': tags,
        'id': csp_instance.name,
        'first_seen': first_seen,
        'namespace': namespace,
        'region': csp_instance.location,
        'provider': ProviderChoice.AZURE,
        'type': Azure(namespace).get_vm_types_in_resource_group(csp_instance.name),
        'default_ttl': default_ttl
    }


def gce_extract_data(csp_instance, namespace: str, default_ttl: int) -> dict:
    tags = {m['key']: m['value'] for m in csp_instance['metadata']
            ['items']} if 'items' in csp_instance['metadata'] else {}
    tags.pop('sshKeys', '')
    first_seen = dateparser.parse(tags.get('openqa_created_date', str(csp_instance['creationTimestamp'])))
    return {
        'tags': tags,
        'id': csp_instance['id'],
        'first_seen': first_seen,
        'namespace': namespace,
        'region': basename(csp_instance['zone']),
        'provider': ProviderChoice.GCE,
        'type': basename(csp_instance['machineType']),
        'default_ttl': default_ttl
    }


def _update_provider(provider: str, namespace: str, default_ttl: int) -> None:
    instance_cnt = Instance.objects.filter(provider=provider, vault_namespace=namespace).update(active=False)
    logger.debug("%d got active state false", instance_cnt)
    if ProviderChoice.from_str(provider) == ProviderChoice.AZURE:
        instances = Azure(namespace).list_resource_groups()
        for i in instances:
            save_or_update_instance(azure_extract_data(i, namespace, default_ttl))
        logger.info("%d resources groups from Azure succesfully processed", len(instances))

    if ProviderChoice.from_str(provider) == ProviderChoice.EC2:
        instance_quantity = 0
        for region in EC2(namespace).all_regions:
            instances = EC2(namespace).list_instances(region=region)
            instance_quantity += len(instances)
            for i in instances:
                save_or_update_instance(ec2_extract_data(i, namespace, region, default_ttl))
        logger.info("%d instances from EC2 successfully processed", instance_quantity)

    if ProviderChoice.from_str(provider) == ProviderChoice.GCE:
        instances = GCE(namespace).list_all_instances()
        for i in instances:
            save_or_update_instance(gce_extract_data(i, namespace, default_ttl))
        logger.info("%d instances from GCE successfully processed", len(instances))
    Instance.objects.filter(provider=provider, vault_namespace=namespace,
                            active=False).update(state=StateChoice.DELETED)


def update_run() -> None:
    '''
    Each update is using Instance.active to mark the model is still availalbe on CSP.
    Instance.state is used to reflect the "local" state, e.g. if someone triggered a delete, the
    state will moved to DELETING. If the instance is gone from CSP, the state will set to DELETED.
    '''
    global RUNNING, LAST_UPDATE
    RUNNING = True
    error_occured = False
    for namespace in PCWConfig.get_namespaces_for('default'):
        default_ttl = PCWConfig.get_feature_property('updaterun', 'default_ttl', namespace)
        for provider in PCWConfig.get_providers_for('default', namespace):
            logger.info("[%s] Check provider %s", namespace, provider)
            try:
                _update_provider(provider, namespace, default_ttl)
            except Exception:
                logger.exception("[%s] Update failed for %s", namespace, provider)
                error_occured = True
                send_mail(f'Error on update {provider} in namespace {namespace}',
                          traceback.format_exc())

    auto_delete_instances()
    send_leftover_notification()
    RUNNING = False
    if not error_occured:
        LAST_UPDATE = datetime.now(timezone.utc)

    if not getScheduler().get_job('update_db'):
        init_cron()


def delete_instance(instance: type[Instance]) -> None:
    if instance.provider == ProviderChoice.AZURE:
        Azure(instance.vault_namespace).delete_resource(instance.instance_id)
    elif instance.provider == ProviderChoice.EC2:
        EC2(instance.vault_namespace).delete_instance(instance.region, instance.instance_id)
    elif instance.provider == ProviderChoice.GCE:
        GCE(instance.vault_namespace).delete_instance(instance.instance_id, instance.region)
    else:
        raise NotImplementedError(
            f"Provider({instance.provider}).delete() isn't implemented")

    instance.state = StateChoice.DELETING
    instance.save()


def auto_delete_instances() -> None:
    for namespace in PCWConfig.get_namespaces_for('default'):
        logger.debug("Running auto_delete_instances for %s", namespace)
        obj = Instance.objects
        obj = obj.filter(state=StateChoice.ACTIVE, vault_namespace=namespace, age__gte=F('ttl')).exclude(ignore=True)
        logger.debug("Found %d instances for deletion", len(obj))
        email_text = set()
        for i in obj:
            logger.debug("[%s] TTL expire for instance %s:%s %s", i.vault_namespace,
                         i.provider, i.instance_id, i.all_time_fields())
            try:
                delete_instance(i)
            except Exception:
                msg = f"[{i.vault_namespace}] Deleting instance ({i.provider}:{i.instance_id}) failed"
                logger.exception(msg)
                email_text.add(f"{msg}\n\n{traceback.format_exc()}")

        if len(email_text) > 0:
            send_mail(f'[{namespace}] Error on auto deleting instance(s)', f"\n{'#'*79}\n".join(email_text))


def is_updating():
    return RUNNING


def last_update():
    return LAST_UPDATE if LAST_UPDATE is not None else ''


def start_update():
    if not RUNNING:
        getScheduler().get_job('update_db').reschedule(trigger='date', run_date=datetime.now(timezone.utc))


def init_cron():
    getScheduler().add_job(update_run, trigger='interval', minutes=45, id='update_db')
