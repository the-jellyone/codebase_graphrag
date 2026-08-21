"""Base model definition."""
from datetime import datetime
from typing import Optional


class BaseModel:
    """Base domain model with common properties."""

    def __init__(self, id: Optional[str] = None, created_at: Optional[datetime] = None):
        self.id = id
        self.created_at = created_at or datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
