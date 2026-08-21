"""Database repository for data persistence."""
import uuid
from typing import Any, Dict, Optional
from backend import config
from backend.exceptions import DatabaseException, NotFoundException

# In-memory store simulation
_STORE: Dict[str, Dict[str, Any]] = {}


def save(entity: Any) -> Any:
    """Save an entity to the database."""
    db_url = config.DB_URL
    if not db_url:
        raise DatabaseException("Database URL is not configured")

    try:
        if not hasattr(entity, "id") or not entity.id:
            entity.id = str(uuid.uuid4())
        
        data = entity.to_dict() if hasattr(entity, "to_dict") else vars(entity)
        _STORE[entity.id] = data
        return entity
    except Exception as exc:
        raise DatabaseException(f"Failed to save entity to {db_url}: {exc}") from exc


def find_by_id(entity_type: str, entity_id: str) -> Dict[str, Any]:
    """Find an entity by ID, honoring connection limits."""
    max_conn = config.MAX_CONNECTIONS
    if max_conn <= 0:
        raise DatabaseException("Connection pool exhausted")

    if entity_id not in _STORE:
        raise NotFoundException(f"{entity_type} with ID '{entity_id}' not found")

    return _STORE[entity_id]
