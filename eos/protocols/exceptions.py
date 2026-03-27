class EosProtocolRunError(Exception):
    pass


class EosProtocolRunStateError(EosProtocolRunError):
    pass


class EosProtocolRunTaskExecutionError(EosProtocolRunError):
    pass


class EosProtocolRunExecutionError(EosProtocolRunError):
    pass


class EosProtocolRunCancellationError(EosProtocolRunError):
    pass
