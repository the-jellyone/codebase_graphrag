"""FastAPI API routes."""
from typing import Dict, Any
from backend.services import user_service, task_service


def create_user(name: str, email: str) -> Dict[str, Any]:
    """API endpoint to create a user."""
    return user_service.create_user(name=name, email=email)


def get_user(user_id: str) -> Dict[str, Any]:
    """API endpoint to get a user by ID."""
    return user_service.get_user(user_id=user_id)


def create_task(title: str, user_id: str) -> Dict[str, Any]:
    """API endpoint to create a task."""
    return task_service.create_task(title=title, user_id=user_id)
