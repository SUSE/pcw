from webui.settings import PCWConfig
from .conftest import set_pcw_ini
import pytest


def test_get_feature_property_with_defaults(pcw_file):
    assert PCWConfig.get_feature_property('cleanup', 'max-images-per-flavor', 'fake') == 1
    assert type(PCWConfig.get_feature_property('cleanup', 'max-images-per-flavor', 'fake')) is int
    assert type(PCWConfig.get_feature_property('cleanup', 'min-image-age-hours', 'fake')) is int
    assert type(PCWConfig.get_feature_property('cleanup', 'max-image-age-hours', 'fake')) is int
    assert PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake') == 'openqa-upload'
    assert type(PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake')) is str

def test_get_feature_property_lookup_error(pcw_file):
    with pytest.raises(LookupError):
        PCWConfig.get_feature_property('notexisting', 'notexisting', 'fake')


def test_get_feature_property_from_pcw_ini_feature(pcw_file):
    set_pcw_ini(pcw_file, """
[cleanup]
max-images-per-flavor = 666
azure-storage-resourcegroup = bla-blub
""")
    assert PCWConfig.get_feature_property('cleanup', 'max-images-per-flavor', 'fake') == 666
    assert type(PCWConfig.get_feature_property('cleanup', 'max-images-per-flavor', 'fake')) is int
    assert PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake') == 'bla-blub'
    assert type(PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'fake')) is str


def test_get_feature_property_from_pcw_ini_with_namespace(pcw_file):
    set_pcw_ini(pcw_file, """
[cleanup]
max-images-per-flavor = 666
azure-storage-resourcegroup = bla-blub

[cleanup.namespace.testns]
max-images-per-flavor = 42
azure-storage-resourcegroup = bla-blub-ns
""")
    cleanup_max_images_per_flavor = PCWConfig.get_feature_property('cleanup', 'max-images-per-flavor', 'testns')
    cleanup_azure_storage_resourcegroup = PCWConfig.get_feature_property('cleanup', 'azure-storage-resourcegroup', 'testns')
    assert cleanup_max_images_per_flavor == 42
    assert type(cleanup_max_images_per_flavor) is int
    assert  cleanup_azure_storage_resourcegroup == 'bla-blub-ns'
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
    assert not {'ec2', 'azure', 'gce'} ^ set(providers)


def test_get_providers_for_existed_feature(pcw_file):
    set_pcw_ini(pcw_file, """
    [providerfeature.namespace.fake]
    providers = azure
    """)
    providers = PCWConfig.get_providers_for('providerfeature', 'fake')
    assert not {'azure'} ^ set(providers)
