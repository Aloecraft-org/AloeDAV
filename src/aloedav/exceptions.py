class AloeDAVClientError(Exception):
    """Base class for all AloeDAV errors."""
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class AuthenticationError(AloeDAVClientError):
    """401/403 Authentication failures."""
    pass

class ResourceNotFound(AloeDAVClientError):
    """404 Resource not found."""
    pass

class PreconditionFailed(AloeDAVClientError):
    """412 Precondition Failed (ETag mismatch)."""
    pass

class WebDAVError(AloeDAVClientError):
    """Generic WebDAV error (5xx, etc)."""
    pass

class ParseError(AloeDAVClientError):
    """
    Malformed iCalendar or vCard content.

    Structural checks raise this rather than asserting: assertions are stripped
    under `python -O`, which would turn a detected structure error into silent
    corruption instead of a failure.
    """
    pass