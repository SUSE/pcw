from webui.PCWConfig import PCWConfig
from .conftest import set_pcw_ini
import pytest


def test_get_feature_property_with_defaults(pcw_file):
    assert type(PCWConfig.get_feature_property('cleanup', 'max-age-hours', 'fake')) is int
    assert type(PCWConfig.get_feature_property('cleanup', 'ec2-max-age-days', 'fake')) is int
    assert type(PCWConfig.get_feature_property('updaterun', 'default_ttl', 'fake')) is int
    assert PCWConfig.get_feature_property('cleanup', 'max-age-hours', 'fake') == 24 * 7
    assert PCWConfig.get_feature_property('cleanup', 'ec2-max-age-days', 'fake') == -1
    assert PCWConfig.get_feature_property('updaterun', 'default_ttl', 'fake') == 44400
    assert PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake') == 'openqa-upload'
    assert type(PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake')) is str


def test_get_feature_property_lookup_error(pcw_file):
    with pytest.raises(LookupError):
        PCWConfig.get_feature_property('notexisting', 'notexisting', 'fake')


def test_get_feature_property_from_pcw_ini_feature(pcw_file):
    set_pcw_ini(pcw_file, """
[cleanup]
max-age-hours = 666
azure-storage-resourcegroup = bla-blub
""")
    assert PCWConfig.get_feature_property('cleanup', 'max-age-hours', 'fake') == 666
    assert PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake') == 'bla-blub'
    assert type(PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake')) is str


def test_get_feature_property_from_pcw_ini_with_namespace(pcw_file):
    set_pcw_ini(pcw_file, """
[cleanup]
max-age-hours = 666
azure-storage-resourcegroup = bla-blub

[cleanup.namespace.testns]
max-age-hours = 42
azure-storage-resourcegroup = bla-blub-ns
""")
    cleanup_max_images_per_flavor = PCWConfig.get_feature_property('cleanup', 'max-age-hours', 'testns')
    cleanup_azure_storage_resourcegroup = PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'testns')
    assert cleanup_max_images_per_flavor == 42
    assert type(cleanup_max_images_per_flavor) is int
    assert cleanup_azure_storage_resourcegroup == 'bla-blub-ns'
    assert type(cleanup_azure_storage_resourcegroup) is str


def test_get_namespaces_for_feature_not_defined(pcw_file):
    namespaces = PCWConfig.get_namespaces_for('test_get_namespaces_for_feature_not_defined')
    assert type(namespaces) is list
    assert len(namespaces) == 0


def test_get_namespaces_for_feature_default_only(pcw_file):
    set_pcw_ini(pcw_file, """
[default]
namespaces = test1, test2
""")
    namespaces = PCWConfig.get_namespaces_for('test_get_namespaces_for_feature_default_only')
    assert type(namespaces) is list
    assert len(namespaces) == 0


def test_get_namespaces_for_feature_default_feature_exists_no_namespace_in_feature(pcw_file):
    set_pcw_ini(pcw_file, """
[default]
namespaces = test1, test2
[no_namespace_in_feature]
some_other_property = value
""")
    namespaces = PCWConfig.get_namespaces_for('no_namespace_in_feature')
    assert type(namespaces) is list
    assert len(namespaces) == 2
    assert not {'test1', 'test2'} ^ set(namespaces)


def test_get_namespaces_for_feature_default_feature_exists_namespace_in_feature(pcw_file):
    set_pcw_ini(pcw_file, """
[default]
namespaces = test1, test2
[no_namespace_in_feature]
some_other_property = value
namespaces = namespace1
""")
    namespaces = PCWConfig.get_namespaces_for('no_namespace_in_feature')
    assert type(namespaces) is list
    assert len(namespaces) == 1
    assert namespaces[0] == 'namespace1'


def test_get_providers_for_not_existed_feature(pcw_file):
    providers = PCWConfig.get_providers_for('get_providers_for', 'not_existent')
    assert type(providers) is list
    assert not {'EC2', 'AZURE', 'GCE'} ^ set(providers)


def test_get_providers_for_existed_feature(pcw_file):
    set_pcw_ini(pcw_file, """
    [providerfeature.namespace.fake]
    providers = azure
    """)
    providers = PCWConfig.get_providers_for('providerfeature', 'fake')
    assert not {'azure'} ^ set(providers)


def test_getBoolean_notdefined(pcw_file):
    assert not PCWConfig.getBoolean('feature/bool_property')


def test_getBoolean_notdefined_namespace(pcw_file):
    assert not PCWConfig.getBoolean('feature/bool_property', 'random_namespace')


def test_getBoolean_defined(pcw_file):
    set_pcw_ini(pcw_file, """
    [feature]
    bool_property = True
    """)
    assert PCWConfig.getBoolean('feature/bool_property')


def test_getBoolean_defined_namespace(pcw_file):
    set_pcw_ini(pcw_file, """
    [feature]
    bool_property = False
    [feature.namespace.random_namespace]
    bool_property = True
    """)
    assert PCWConfig.getBoolean('feature/bool_property', 'random_namespace')


def test_getBoolean_namespace_but_not_defined(pcw_file):
    set_pcw_ini(pcw_file, """
    [feature]
    bool_property = True
    [feature.namespace.random_namespace]
    providers = azure
    """)
    assert PCWConfig.getBoolean('feature/bool_property', 'random_namespace')


def test_get_k8s_clusters_for_provider(pcw_file):
    set_pcw_ini(pcw_file, """
    [k8sclusters]
    namespaces=random_namespace

    [k8sclusters.namespace.random_namespace]
    azure-clusters = resource_group:cluster_name
    """)
    clusters = PCWConfig.get_k8s_clusters_for_provider('random_namespace', 'azure')
    assert len(clusters) == 1
    assert clusters[0]['resource_group'] == 'resource_group'
    assert clusters[0]['cluster_name'] == 'cluster_name'


def test_get_k8s_clusters_for_provider_not_section_defined(pcw_file):
    set_pcw_ini(pcw_file, "")
    with pytest.raises(LookupError):
        PCWConfig.get_k8s_clusters_for_provider('random_namespace', 'azure')


def test_get_k8s_clusters_for_provider_no_azure_clusters_defined(pcw_file):
    set_pcw_ini(pcw_file, """
    [k8sclusters]
    namespaces=random_namespace

    [k8sclusters.namespace.random_namespace]
    """)
    with pytest.raises(LookupError):
        PCWConfig.get_k8s_clusters_for_provider('random_namespace', 'azure')


def test_get_k8s_clusters_for_provider_azure_clusters_empty(pcw_file):
    set_pcw_ini(pcw_file, """
    [k8sclusters]
    namespaces=random_namespace

    [k8sclusters.namespace.random_namespace]
    azure-clusters =
    """)
    with pytest.raises(ValueError):
        PCWConfig.get_k8s_clusters_for_provider('random_namespace', 'azure')


def test_get_k8s_clusters_for_provider_azure_clusters_invalid(pcw_file):
    set_pcw_ini(pcw_file, """
    [k8sclusters]
    namespaces=random_namespace

    [k8sclusters.namespace.random_namespace]
    azure-clusters = not_valid_format
    """)
    with pytest.raises(ValueError):
        PCWConfig.get_k8s_clusters_for_provider('random_namespace', 'azure')
