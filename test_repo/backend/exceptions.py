"""Custom application exceptions."""


class BaseAppException(Exception):
    """Base exception for application."""
    pass


class NotFoundException(BaseAppException):
    """Raised when an entity is not found in storage."""
    pass


class DatabaseException(BaseAppException):
    """Raised when a database operation fails."""
    pass


class ValidationException(BaseAppException):
    """Raised when data validation fails."""
    pass
