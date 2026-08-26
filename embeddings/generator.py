"""
Local embedding generator using Ollama.

Communicates with the local Ollama instance to generate dense vector embeddings
for code nodes. Supports batching, dimension discovery, and fallback handling.
"""

from __future__ import annotations
import os
from typing import Optional, Sequence
import ollama
from loguru import logger
from dotenv import load_dotenv

from ingestion.models import ParsedNode
from embeddings.formatter import format_node_for_embedding, should_embed_node

# Load environment variables
load_dotenv()

DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")



class OllamaEmbeddingGenerator:
    """Generates dense vector embeddings using local Ollama models."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.model_name = model_name or DEFAULT_EMBEDDING_MODEL
        self.base_url = base_url or DEFAULT_OLLAMA_URL
        self.client = ollama.Client(host=self.base_url)
        self._cached_dimension: Optional[int] = None

    def embed_text(self, text: str) -> list[float]:
        """Generate vector embedding for a single text string."""
        if not text or not text.strip():
            # Return zero vector with known dimension if text is empty
            dim = self.get_dimension()
            return [0.0] * dim

        try:
            response = self.client.embeddings(model=self.model_name, prompt=text)
            embedding = response["embedding"]
            if not self._cached_dimension:
                self._cached_dimension = len(embedding)
            return embedding
        except Exception as exc:
            logger.error(f"Failed to generate embedding for model '{self.model_name}': {exc}")
            raise

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate vector embeddings for a list of texts."""
        return [self.embed_text(t) for t in texts]

    def embed_nodes(self, nodes: list[ParsedNode]) -> list[ParsedNode]:
        """
        Embed all eligible nodes (Function, Class) in-place and populate node.embedding.
        """
        to_embed = [n for n in nodes if should_embed_node(n)]
        logger.info(f"Generating embeddings for {len(to_embed)} code nodes using '{self.model_name}'...")

        for idx, node in enumerate(to_embed, 1):
            text_repr = format_node_for_embedding(node)
            node.embedding = self.embed_text(text_repr)
            if idx % 10 == 0 or idx == len(to_embed):
                logger.debug(f"Embedded {idx}/{len(to_embed)} nodes")

        logger.success(f"Successfully generated embeddings for {len(to_embed)} nodes")
        return nodes

    def get_dimension(self) -> int:
        """Discover the embedding dimension of the configured model."""
        if self._cached_dimension is not None:
            return self._cached_dimension

        # Probe with a small test string
        sample_emb = self.embed_text("test probe")
        self._cached_dimension = len(sample_emb)
        logger.info(f"Detected embedding dimension for '{self.model_name}': {self._cached_dimension}")
        return self._cached_dimension
