"""
Neo4j driver connection manager.

Handles connection pooling, authentication, health checks, and query execution.
"""

from __future__ import annotations
import os
from typing import Any, Optional
from neo4j import GraphDatabase, Driver, Session
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

DEFAULT_NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


class Neo4jConnection:
    """Manages the Neo4j database driver and transaction sessions."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or DEFAULT_NEO4J_URI
        self.user = user or DEFAULT_NEO4J_USER
        self.password = password or DEFAULT_NEO4J_PASSWORD
        self._driver: Optional[Driver] = None

    def get_driver(self) -> Driver:
        """Get or initialize the Neo4j Driver instance."""
        if self._driver is None:
            logger.info(f"Connecting to Neo4j at {self.uri} (user: {self.user})...")
            try:
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                )
                self.verify_connectivity()
                logger.success("Connected to Neo4j successfully")
            except Exception as exc:
                logger.error(f"Failed to connect to Neo4j at {self.uri}: {exc}")
                raise
        return self._driver

    def verify_connectivity(self) -> bool:
        """Check if the Neo4j database is accessible and credentials are valid."""
        if self._driver is None:
            self.get_driver()
        assert self._driver is not None
        self._driver.verify_connectivity()
        return True

    def close(self) -> None:
        """Close the driver and release resources."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
            logger.info("Neo4j driver closed")

    def run_query(self, query: str, parameters: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """Execute a Cypher query and return the results as a list of dictionaries."""
        driver = self.get_driver()
        with driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def execute_write(self, func, *args, **kwargs):
        """Execute a transactional write function."""
        driver = self.get_driver()
        with driver.session() as session:
            return session.execute_write(func, *args, **kwargs)
