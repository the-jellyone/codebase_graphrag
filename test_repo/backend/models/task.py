"""Task domain model."""
from typing import Optional
from datetime import datetime
from backend.models.base import BaseModel


class Task(BaseModel):
    """Task entity representing a user work item."""

    def __init__(
        self,
        id: Optional[str] = None,
        title: str = "",
        user_id: str = "",
        completed: bool = False,
        created_at: Optional[datetime] = None,
    ):
        super().__init__(id=id, created_at=created_at)
        self.title = title
        self.user_id = user_id
        self.completed = completed

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update(
            {
                "title": self.title,
                "user_id": self.user_id,
                "completed": self.completed,
            }
        )
        return data
