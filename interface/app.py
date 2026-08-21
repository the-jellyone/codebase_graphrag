"""Codebase Graph RAG - Streamlit Interface."""
import streamlit as st

st.set_page_config(
    page_title="Codebase Graph RAG",
    page_icon="🕸️",
    layout="wide",
)

st.title("🕸️ Codebase Graph RAG")
st.markdown(
    """
    Welcome to **Codebase Graph RAG** — a local, offline knowledge graph RAG system for multi-hop code reasoning.
    
    ### System Status
    - **Neo4j**: Configured
    - **ChromaDB**: Configured
    - **Ollama**: Configured
    """
)
