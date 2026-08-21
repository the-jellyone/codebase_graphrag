"""Application configuration."""
import os

DB_URL: str = os.getenv("DB_URL", "sqlite:///./test.db")
MAX_CONNECTIONS: int = int(os.getenv("MAX_CONNECTIONS", "10"))
DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
