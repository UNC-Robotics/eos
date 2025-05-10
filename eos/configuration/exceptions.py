from eos.devices.exceptions import EosDeviceError


class EosConfigurationError(Exception):
    pass


class EosMissingConfigurationError(Exception):
    pass


class EosExperimentConfigurationError(Exception):
    pass


class EosLabConfigurationError(Exception):
    pass


class EosContainerConfigurationError(Exception):
    pass


class EosTaskValidationError(Exception):
    pass


class EosDynamicParameterConfigurationError(Exception):
    pass


class EosTaskGraphError(Exception):
    pass


class EosTaskPluginError(Exception):
    pass


class EosCampaignOptimizerPluginError(Exception):
    pass


class EosCampaignOptimizerNotFoundError(Exception):
    pass


class EosDevicePluginError(EosDeviceError):
    pass
