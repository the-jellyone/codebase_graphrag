"""Task service business logic."""
from typing import Dict, Any
from backend.db import repository
from backend.utils import validators
from backend.models.task import Task
from backend.exceptions import NotFoundException, ValidationException
from backend.services import user_service


def create_task(title: str, user_id: str) -> Dict[str, Any]:
    """Create and persist a task for a valid user."""
    validators.validate_string(title, "title")
    validators.validate_string(user_id, "user_id")

    # Verify user exists (cross-service call)
    user_service.get_user(user_id)

    task = Task(title=title, user_id=user_id, completed=False)
    saved_task = repository.save(task)
    return saved_task.to_dict()
