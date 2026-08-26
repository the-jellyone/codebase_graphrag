"""
Centralized client factory for Ollama and Neo4j.

Provides clean, unified access to:
- Embedding model (vector generation)
- LLM chat model (with real-time token streaming)
- Neo4j graph database driver
"""

from __future__ import annotations
import os
from typing import Generator, Any
import ollama
from neo4j import GraphDatabase, Driver
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
LLM_MODEL = os.getenv("LLM_MODEL")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")



def get_embedder(model_name: str | None = None) -> Any:
    """Return an embedding function that converts text into a float vector."""
    target_model = model_name or EMBEDDING_MODEL
    client = ollama.Client(host=OLLAMA_BASE_URL)

    def embed(text: str) -> list[float]:
        if not text or not text.strip():
            return []
        try:
            response = client.embeddings(model=target_model, prompt=text)
            return response["embedding"]
        except Exception as exc:
            logger.error(f"Embedding failed with model '{target_model}': {exc}")
            raise

    return embed


def get_llm(model_name: str | None = None) -> Any:
    """Return a chat generator function that streams tokens from Ollama."""
    target_model = model_name or LLM_MODEL
    client = ollama.Client(host=OLLAMA_BASE_URL)

    def stream_chat(prompt: str, system_prompt: str | None = None) -> Generator[str, None, None]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            # pyrefly: ignore [no-matching-overload]
            stream = client.chat(
                model=target_model,
                messages=messages,
                stream=True,
                options={
                    "temperature": 0.2,
                    "num_ctx": 8192,
                    "num_predict": 1024,
                    "top_p": 0.9,
                },
            )
            for chunk in stream:
                yield chunk["message"]["content"]
        except Exception as exc:
            logger.error(f"LLM streaming failed with model '{target_model}': {exc}")
            raise

    return stream_chat


def get_neo4j() -> Driver:
    """Return a configured Neo4j driver instance."""
    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
