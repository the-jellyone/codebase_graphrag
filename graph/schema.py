"""
Neo4j schema, constraints, and native vector index setup.

Configures:
1. Unique Constraints: ensures node `id` is unique across labels.
2. Native Vector Indexes: creates Neo4j 5+ Vector Indexes on Function and Class embeddings.
"""

from __future__ import annotations
from typing import Optional
from neo4j import Driver
from loguru import logger

from ingestion.models import NodeType

NODE_LABELS = [
    NodeType.FUNCTION.value,
    NodeType.CLASS.value,
    NodeType.MODULE.value,
    NodeType.EXCEPTION.value,
    NodeType.CONFIG.value,
]

FUNCTION_VECTOR_INDEX_NAME = "function_vector_index"
CLASS_VECTOR_INDEX_NAME = "class_vector_index"


def setup_schema(
    driver: Driver,
    embedding_dimension: int = 1536,
    similarity_function: str = "cosine",
) -> None:
    """
    Initialize all uniqueness constraints and vector indexes in Neo4j.
    """
    with driver.session() as session:
        # 1. Uniqueness Constraints
        for label in NODE_LABELS:
            constraint_name = f"unique_{label.lower()}_id"
            query = f"""
            CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
            FOR (n:{label}) REQUIRE n.id IS UNIQUE
            """
            session.run(query)
            logger.debug(f"Ensured constraint: {constraint_name}")

        # 2. Vector Index for Functions
        fn_vector_query = f"""
        CREATE VECTOR INDEX {FUNCTION_VECTOR_INDEX_NAME} IF NOT EXISTS
        FOR (f:Function) ON (f.embedding)
        OPTIONS {{
          indexConfig: {{
            `vector.dimensions`: {embedding_dimension},
            `vector.similarity_function`: '{similarity_function}'
          }}
        }}
        """
        session.run(fn_vector_query)
        logger.debug(f"Ensured vector index: {FUNCTION_VECTOR_INDEX_NAME} (dim={embedding_dimension})")

        # 3. Vector Index for Classes
        cls_vector_query = f"""
        CREATE VECTOR INDEX {CLASS_VECTOR_INDEX_NAME} IF NOT EXISTS
        FOR (c:Class) ON (c.embedding)
        OPTIONS {{
          indexConfig: {{
            `vector.dimensions`: {embedding_dimension},
            `vector.similarity_function`: '{similarity_function}'
          }}
        }}
        """
        session.run(cls_vector_query)
        logger.debug(f"Ensured vector index: {CLASS_VECTOR_INDEX_NAME} (dim={embedding_dimension})")

    logger.success("Neo4j constraints and vector indexes initialized successfully")


def clear_database(driver: Driver) -> None:
    """Delete all nodes and relationships from the database (useful for fresh re-indexing)."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    logger.warning("Cleared all nodes and relationships from Neo4j database")
