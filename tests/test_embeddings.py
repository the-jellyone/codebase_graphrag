"""
Tests for Ollama embeddings generator, node formatting, and vector search sanity.

Run with:
  pytest tests/test_embeddings.py -v
"""

import math
import pytest
from ingestion.models import ParsedNode, NodeType
from embeddings.formatter import format_node_for_embedding, should_embed_node
from embeddings.generator import OllamaEmbeddingGenerator


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


@pytest.fixture(scope="module")
def embedder():
    """Create OllamaEmbeddingGenerator instance and verify connectivity."""
    gen = OllamaEmbeddingGenerator()
    try:
        dim = gen.get_dimension()
        assert dim > 0
    except Exception as exc:
        pytest.skip(f"Ollama is not reachable or model '{gen.model_name}' is not pulled: {exc}")
    return gen


class TestNodeFormatting:
    def test_format_function_node(self):
        node = ParsedNode(
            id="services/auth.py::login_user",
            type=NodeType.FUNCTION,
            name="login_user",
            file="services/auth.py",
            line=10,
            docstring="Authenticate user with password hash.",
            source_code="def login_user(username, password):\n    return verify(username, password)",
        )
        assert should_embed_node(node) is True
        text = format_node_for_embedding(node)
        assert "[Function] login_user" in text
        assert "File: services/auth.py:10" in text
        assert "Docstring: Authenticate user with password hash." in text
        assert "Source:" in text

    def test_should_not_embed_module_or_exception(self):
        mod_node = ParsedNode(
            id="services/auth.py",
            type=NodeType.MODULE,
            name="auth",
            file="services/auth.py",
        )
        assert should_embed_node(mod_node) is False


class TestOllamaEmbeddingGenerator:
    def test_embed_text_dimension(self, embedder):
        vec = embedder.embed_text("def authenticate_user(token: str) -> bool:")
        assert isinstance(vec, list)
        assert len(vec) == embedder.get_dimension()
        assert all(isinstance(x, float) for x in vec)

    def test_embed_nodes_in_place(self, embedder):
        nodes = [
            ParsedNode(
                id="backend/services/user_service.py::create_user",
                type=NodeType.FUNCTION,
                name="create_user",
                file="backend/services/user_service.py",
                line=5,
                source_code="def create_user(name: str): return db.save(name)",
            ),
            ParsedNode(
                id="backend/services/user_service.py",
                type=NodeType.MODULE,
                name="user_service",
                file="backend/services/user_service.py",
            ),
        ]
        embedder.embed_nodes(nodes)
        # Function node should have embedding populated
        assert nodes[0].embedding is not None
        assert len(nodes[0].embedding) == embedder.get_dimension()
        # Module node should NOT be embedded
        assert nodes[1].embedding is None

    def test_semantic_similarity(self, embedder):
        """Semantic search sanity: 'user creation' should be closer to create_user than calculate_primes."""
        query_vec = embedder.embed_text("create and register new user account in database")
        user_node_vec = embedder.embed_text("def create_user(email: str, name: str):\n    db.users.insert({'email': email})")
        math_node_vec = embedder.embed_text("def calculate_primes(limit: int):\n    return [x for x in range(2, limit) if is_prime(x)]")

        sim_user = cosine_similarity(query_vec, user_node_vec)
        sim_math = cosine_similarity(query_vec, math_node_vec)

        assert sim_user > sim_math, f"Expected user similarity ({sim_user:.4f}) > math similarity ({sim_math:.4f})"
