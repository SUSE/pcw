from .vault import GCECredential
from .provider import Provider, Image
import googleapiclient.discovery
from google.oauth2 import service_account
from dateutil.parser import parse
from .decorators import filterService
from googleapiclient.errors import HttpError
import re


class GCE(Provider):
    __instances = dict()

    def __new__(cls, vault_namespace, *args, **kwargs):
        if vault_namespace in GCE.__instances:
            return GCE.__instances[vault_namespace]
        GCE.__instances[vault_namespace] = object.__new__(cls)
        return GCE.__instances[vault_namespace]

    def __init__(self, namespace):
        super().__init__(namespace)
        self.__credentials = GCECredential(namespace)
        self.__compute_client = None
        self.__iam_client = None
        self.__project = None
        self.credentials = None

    def compute_client(self):
        if self.__credentials.isExpired():
            self.__credentials.renew()
            self.__compute_client = None
            self.credentials = None
        self.__project = self.__credentials.getPrivateKeyData()["project_id"]
        if self.__compute_client is None:
            self.credentials = service_account.Credentials.from_service_account_info(
                self.__credentials.getPrivateKeyData()
            )
            self.__compute_client = googleapiclient.discovery.build(
                "compute", "v1", credentials=self.credentials, cache_discovery=False
            )
        return self.__compute_client

    def iam_client(self):
        if self.__credentials.isExpired():
            self.__credentials.renew()
            self.__iam_client = None
            self.credentials = None
        self.__project = self.__credentials.getPrivateKeyData()["project_id"]
        if self.__iam_client is None:
            self.credentials = service_account.Credentials.from_service_account_info(
                self.__credentials.getPrivateKeyData()
            )
            self.__iam_client = googleapiclient.discovery.build(
                "iam", "v1", credentials=self.credentials, cache_discovery=True
            )
        return self.__iam_client

    def list_instances(self, zone):
        """ List all instances by zone."""
        result = []
        request = (
            self.compute_client().instances().list(project=self.__project, zone=zone)
        )
        while request is not None:
            response = request.execute()
            if "items" in response:
                result += response["items"]
            request = (
                self.compute_client()
                .instances()
                .list_next(previous_request=request, previous_response=response)
            )
        return result

    def list_all_instances(self):
        result = []
        for region in self.list_regions():
            for zone in self.list_zones(region):
                result += self.list_instances(zone=zone)
        return result

    def list_regions(self):
        """Walk through all regions->zones and collect all instances to return them as list.
        @see https://cloud.google.com/compute/docs/reference/rest/v1/instances/list#examples"""
        result = []
        request = self.compute_client().regions().list(project=self.__project)
        while request is not None:
            response = request.execute()

            for region in response["items"]:
                result.append(region["name"])
            request = (
                self.compute_client()
                .regions()
                .list_next(previous_request=request, previous_response=response)
            )
        return result

    def list_zones(self, region):
        region = (
            self.compute_client()
            .regions()
            .get(project=self.__project, region=region)
            .execute()
        )
        return [GCE.url_to_name(z) for z in region["zones"]]

    def delete_instance(self, instance_id, zone):
        if self.dry_run:
            self.log_info(
                "Deletion of instance {} skipped due to dry run mode", instance_id
            )
        else:
            self.compute_client().instances().delete(
                project=self.__project, zone=zone, instance=instance_id
            ).execute()

    @staticmethod
    def url_to_name(url):
        return url[url.rindex("/")+1:]

    def parse_image_name(self, img_name):
        regexes = [
            # sles12-sp5-gce-x8664-0-9-1-byos-build1-56
            re.compile(
                r"""^sles
                    (?P<version>\d+(-sp\d+)?)
                    -
                    (?P<flavor>gce)
                    -
                    (?P<arch>[^-]+)
                    -
                    (?P<kiwi>\d+-\d+-\d+)
                    -
                    (?P<type>(byos|on-demand))
                    -build
                    (?P<build>\d+-\d+)
                    """,
                re.RegexFlag.X,
            ),
            # sles15-sp2-byos-x8664-0-9-3-gce-build1-10
            # sles15-sp2-x8664-0-9-3-gce-build1-10
            re.compile(
                r"""^sles
                    (?P<version>\d+(-sp\d+)?)
                    (-(?P<type>[-\w]+))?
                    -
                    (?P<arch>[^-]+)
                    -
                    (?P<kiwi>\d+-\d+-\d+)
                    -
                    (?P<flavor>gce)
                    -
                    build
                    (?P<build>\d+-\d+)
                    """,
                re.RegexFlag.X,
            ),
            # sles15-sp1-gce-byos-x8664-1-0-5-build1-101
            re.compile(
                r"""^sles
                (?P<version>\d+(-sp\d+)?)
                (-(?P<flavor>gce))?
                -
                (?P<type>[-\w]+)
                -
                (?P<arch>[^-]+)
                -
                (?P<kiwi>\d+-\d+-\d+)
                -
                build
                (?P<build>\d+-\d+)
                """,
                re.RegexFlag.X,
            ),
        ]
        return self.parse_image_name_helper(img_name, regexes)

    def cleanup_all(self):
        images = list()
        request = self.compute_client().images().list(project=self.__project)
        while request is not None:
            response = request.execute()
            if "items" not in response:
                break
            for image in response["items"]:
                # creation:2019-11-04T14:23:06.372-08:00
                # name:sles12-sp5-gce-x8664-0-9-1-byos-build1-56
                m = self.parse_image_name(image["name"])
                if m:
                    images.append(
                        Image(
                            image["name"],
                            flavor=m["key"],
                            build=m["build"],
                            date=parse(image["creationTimestamp"]),
                        )
                    )
                    self.log_dbg(
                        "Image {} is candidate for deletion with build {}",
                        image["name"],
                        m["build"],
                    )
                else:
                    self.log_err("Unable to parse image name '{}'", image["name"])

            request = (
                self.compute_client()
                .images()
                .list_next(previous_request=request, previous_response=response)
            )

        keep_images = self.get_keeping_image_names(images)

        for img in [i for i in images if i.name not in keep_images]:
            self.log_info("Delete image '{}'", img.name)
            if self.dry_run:
                self.log_info(
                    "Deletion of image {} skipped due to dry run mode", img.name
                )
            else:
                request = (
                    self.compute_client()
                    .images()
                    .delete(project=self.__project, image=img.name)
                )
                response = request.execute()
                if "error" in response:
                    for e in response["error"]["errors"]:
                        self.log_err(e["message"])
                if "warnings" in response:
                    for w in response["warnings"]:
                        self.log_warn(w["message"])
        self.cleanup_serviceaccounts()

    def cleanup_serviceaccounts(self):
        self.log_info("## GCE Vault key cleaning - {} ##".format(self.__project))

        # Get service account emails
        service_accounts_filtered_by_email = self.get_service_accounts()
        # For each email found return the ones with associated old date
        service_accounts_filtered_by_email_filtered = self.filter_by_times(service_accounts_filtered_by_email)
        self.delete_service_accounts(service_accounts_filtered_by_email_filtered)

    @filterService(name='vaultopenqa')
    def get_service_accounts(self):
        ''' Returns a list of the emails of the Service Accounts

        The request is using the resource name of the project associated with
        the service accounts. This returns a list of dict items, which are
        also not vault related.
        The objects returned in chunks which contain a `nextPageToken`
        to the next page. The `get_service_accounts` parses each page
        and returns the full list. Subsequently, the list is filtered to return
        only emails correlated with vault Service Accounts
        '''
        service_accounts_filtered_by_email = []
        req = self.iam_client().projects().serviceAccounts().list(
            name='projects/suse-sle-qa')

        while True:
            resp = req.execute()
            service_accounts_filtered_by_email += [service_account['email']
                                                   for service_account in resp.get('accounts', [])]

            req = self.iam_client().projects().serviceAccounts().list_next(
                previous_request=req, previous_response=resp)
            if req is None:
                return tuple(set(service_accounts_filtered_by_email))

    def filter_by_times(self, vault_account_tuple, time_limit=24):
        '''Returns a list of the emails of the Service Accounts filtered by _time_limit_

        Makes a API request to the ServiceAccount to list all the keys associated with
        the corresponding email of the service.
        The respond returns a json in the format
        _{'keys': [
           {'name': 'projects/suse-sle-qa/serviceAccounts/{ACCOUNT}/keys/{KEY_HASH} # the full path for a key,
            'validAfterTime': '2021-11-15T12:13:43Z', # age of the key
            'validBeforeTime': '2021-12-02T12:13:43Z',
            'keyAlgorithm': 'KEY_ALG_RSA_2048',
            'keyOrigin': 'GOOGLE_PROVIDED',
            'keyType': 'USER_MANAGED'}
         ]}

        Using `validAfterTime` the function calculate which Service Accounts
        should be deleted. The actual delete function takes the email in its
        request, so the `filter_by_times` has to returned them
        corelated email addresses of the `service_resp['keys']`

        Parameters
        ----------
        vault_account_tuple : googleapiclient.discovery.Resource, required
            The IAM Service Account instance
        time_limit : int
            the number of hours where the Service Accounts are keep been
            ignored from the cleanup job
        '''
        from datetime import datetime, timedelta
        time_limit = datetime.now() - timedelta(hours=time_limit)
        dt_frm = datetime.fromisoformat
        filtered_service_accounts = []
        for email in vault_account_tuple:
            service_resp = self.iam_client().projects().serviceAccounts().keys().list(
                name='projects/-/serviceAccounts/{}'.format(email)).execute()
            filtered_service_accounts += [k['name'] for k in service_resp['keys'] if dt_frm(
                    k['validAfterTime'][:-1]) < time_limit]
        return list(filter(lambda e: e in str(filtered_service_accounts), vault_account_tuple))

    def delete_service_accounts(self, service_accounts):
        ''' Deletes a list of vault keys

        Expects _iam_service_ of type *googleapiclient.discovery.Resource*
        and _service_accounts_ list of strings.

        A short comment from the documentation. - Deleting a service account
        key does not revoke short-lived credentials
        that have been issued based on the service account key.

        Parameters
        ----------
        service_accounts : list, required
            A list of keys to delete. This is retrieved by the _accounts_ of
            the *get_service_accounts* which is the email field.

        Raises
        ------
        TypeError
            This will raised when the _service_accounts_ will not match the expected pattern in the _name_
        HttpError
            Http Respond Errors
        '''
        if (len(service_accounts) < 1):
            self.log_info("Nothing to delete")
        else:
            for account_email in list(service_accounts):
                if self.dry_run:
                    self.log_warn(
                        "Deletion of vault Service Account {} skipped due to dry run mode"
                        .format(account_email))
                else:
                    try:
                        # TODO: if deletion needs key removal first
                        # iam_service.projects().serviceAccounts().keys().delete(
                        #     name=service_accounts).execute()
                        self.iam_client().projects().serviceAccounts().delete(
                            name='projects/-/serviceAccounts/{}'.format(account_email)).execute()
                    except (TypeError, HttpError) as err:
                        self.log_err("Fail to delete Service Account {} \n{}".format(account_email, err))
