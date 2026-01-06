class AloeError(Exception):
    """Base class for all AloeDAV errors."""
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text

class AuthenticationError(AloeError):
    """401/403 Authentication failures."""
    pass

class ResourceNotFound(AloeError):
    """404 Resource not found."""
    pass

class PreconditionFailed(AloeError):
    """412 Precondition Failed (ETag mismatch)."""
    pass

class WebDAVError(AloeError):
    """Generic WebDAV error (5xx, etc)."""
    pass