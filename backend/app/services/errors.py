class ServiceNotConfiguredError(RuntimeError):
    """Raised when an external AI service has no credentials or contract yet."""


class ServiceUnavailableError(RuntimeError):
    """Raised when an optional runtime dependency (for example YOLO) is missing."""
