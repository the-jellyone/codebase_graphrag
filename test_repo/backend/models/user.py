"""User domain model."""
from typing import Optional
from datetime import datetime
from backend.models.base import BaseModel


class User(BaseModel):
    """User entity representing an account."""

    def __init__(
        self,
        id: Optional[str] = None,
        name: str = "",
        email: str = "",
        created_at: Optional[datetime] = None,
    ):
        super().__init__(id=id, created_at=created_at)
        self.name = name
        self.email = email

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({"name": self.name, "email": self.email})
        return data
