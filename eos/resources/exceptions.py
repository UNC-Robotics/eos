class EosResourceError(Exception):
    """Base exception for resource-related errors."""


class EosResourceStateError(EosResourceError):
    """Exception raised when a resource is in an invalid state."""


class EosResourceAllocationError(EosResourceError):
    """Exception raised when a resource allocation operation fails."""
