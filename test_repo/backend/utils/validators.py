"""Validation utility functions."""
import re
from backend.exceptions import ValidationException


def validate_email(email: str) -> bool:
    """Validate format of an email address."""
    if not email or not isinstance(email, str):
        raise ValidationException("Email cannot be empty")
    email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    if not re.match(email_regex, email):
        raise ValidationException(f"Invalid email format: {email}")
    return True


def validate_string(val: str, field_name: str) -> bool:
    """Validate that a string field is not empty."""
    if not val or not isinstance(val, str) or not val.strip():
        raise ValidationException(f"Field '{field_name}' cannot be empty")
    return True
