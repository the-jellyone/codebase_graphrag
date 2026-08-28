"""
Central config — single place for all env-driven settings.

Every module that needs a model name or connection string imports from here.
Changing a value in .env propagates everywhere automatically.

Usage:
    from config import OLLAMA_LLM_MODEL, OLLAMA_EMBED_MODEL
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Ollama models ────────────────────────────────────────────────────────────
OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", os.getenv("LLM_MODEL", "granite4.1:3b"))
OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b"))

# ── Neo4j ────────────────────────────────────────────────────────────────────
NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "neo4j")

# ── Ollama base URL ──────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Global think=False default for Ollama ─────────────────────────────────────
import ollama

_original_ollama_chat = ollama.chat


def _chat_with_think_default(*args, **kwargs):
    """Wrap ollama.chat to default think=False across all agent nodes."""
    if "think" not in kwargs:
        kwargs["think"] = False
    try:
        return _original_ollama_chat(*args, **kwargs)
    except TypeError:
        # Fallback for SDK versions accepting think inside options dict
        kwargs.pop("think", None)
        opts = dict(kwargs.get("options") or {})
        if "think" not in opts:
            opts["think"] = False
        kwargs["options"] = opts
        return _original_ollama_chat(*args, **kwargs)


ollama.chat = _chat_with_think_default
