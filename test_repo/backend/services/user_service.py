"""User service business logic."""
from typing import Dict, Any
from backend.db import repository
from backend.utils import validators
from backend.models.user import User
from backend.exceptions import NotFoundException, ValidationException


def create_user(name: str, email: str) -> Dict[str, Any]:
    """Create and persist a new user."""
    validators.validate_email(email)
    validators.validate_string(name, "name")

    user = User(name=name, email=email)
    saved_user = repository.save(user)
    return saved_user.to_dict()


def get_user(user_id: str) -> Dict[str, Any]:
    """Retrieve an existing user by ID."""
    validators.validate_string(user_id, "user_id")
    return repository.find_by_id("User", user_id)
