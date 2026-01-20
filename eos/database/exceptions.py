class EosFileDbError(Exception):
    pass


class DbConnectionError(Exception):
    """Raised when database connection fails (e.g., timeout, connection refused)."""
