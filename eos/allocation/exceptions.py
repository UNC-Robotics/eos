class EosAllocationRequestError(Exception):
    """Base exception for allocation request errors."""


class EosDeviceAllocatedError(EosAllocationRequestError):
    """Exception raised when a device is already allocated."""


class EosDeviceNotFoundError(EosAllocationRequestError):
    """Exception raised when a device is not found."""


class EosResourceAllocatedError(EosAllocationRequestError):
    """Exception raised when a resource is already allocated."""


class EosResourceNotFoundError(EosAllocationRequestError):
    """Exception raised when a resource is not found."""
