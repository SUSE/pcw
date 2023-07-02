from enum import Enum


class ChoiceEnum(Enum):
    @classmethod
    def choices(cls):
        return [(i.name, i.value) for i in cls]

    def __str__(self):
        return self.name

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return not self == other


class ProviderChoice(ChoiceEnum):
    GCE = 'Google'
    EC2 = 'EC2'
    AZURE = 'Azure'
    OSTACK = 'Openstack'

    @staticmethod
    def from_str(provider):
        if provider.upper() == ProviderChoice.GCE:
            return ProviderChoice.GCE
        elif provider.upper() == ProviderChoice.EC2:
            return ProviderChoice.EC2
        elif provider.upper() == ProviderChoice.AZURE:
            return ProviderChoice.AZURE
        elif provider.upper() == ProviderChoice.OSTACK:
            return ProviderChoice.OSTACK
        else:
            raise ValueError(f"{provider} is not convertable to ProviderChoice")


class StateChoice(ChoiceEnum):
    UNK = 'unkown'
    ACTIVE = 'active'
    DELETING = 'deleting'
    DELETED = 'deleted'
