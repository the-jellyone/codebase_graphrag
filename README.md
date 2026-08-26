# Codebase Graph RAG 🕸️

A 100% local, fully offline **Codebase Intelligence Engine**. Ingests multi-language code repositories (Python, TypeScript), builds a Knowledge Graph in Neo4j with native vector indexing, and performs Conversational Graph RAG to answer multi-hop architectural questions.

---

## Architecture Overview

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                   REACT + TAILWIND FRONTEND (`frontend/`)               │
 │                   URL: http://localhost:5173                            │
 │                                                                         │
 │  • Dark-Mode Chat Interface (ChatGPT / Claude style)                    │
 │  • Real-Time SSE Token Streaming                                        │
 │  • Conversational Memory & Multi-turn Chat                              │
 │  • Retrieved Subgraph Accordion + Timing Metrics                        │
 │  • Target Repo Indexing Controls                                        │
 └────────────────────────────────────┬────────────────────────────────────┘
                                      │ HTTP / SSE Streams (Port 8000)
                                      ▼
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                   FASTAPI BACKEND (`interface/api.py`)                  │
 │                   URL: http://localhost:8000                            │
 │                                                                         │
 │  • Conversational Query Rewriter (Resolves "it", "this file" via history) │
 │  • Hybrid Graph RAG Engine (`retrieval/retriever.py`)                   │
 │    Vector Search (`qwen3-embed-0.6B`) → Seed Nodes → Cypher 2-Hop        │
 │  • Local Ollama Streaming Engine (`qwen3-4b`)                           │
 └─────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

1. **Docker**: For running Neo4j 5.x graph database.
2. **Node.js (v18+)**: For running the React frontend.
3. **Python (3.10+)**: For the backend pipeline.
4. **Ollama**: Running locally with pulled models:
   ```bash
   ollama pull qwen3-embed-0.6B
   ollama pull qwen3-4b
   ```

---

## Setup & Running Guide

### Step 1: Start Neo4j via Docker
```bash
docker compose up -d neo4j
```
- **Neo4j Browser**: [http://localhost:7474](http://localhost:7474) (Credentials: `neo4j` / `password`)

---

### Step 2: Start FastAPI Backend

```bash
# Activate virtualenv (or create if needed: python3 -m venv venv)
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Launch FastAPI Server
python -m interface.api
```
- **Backend Server**: [http://localhost:8000](http://localhost:8000)
- **Healthcheck**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

### Step 3: Start React Frontend

In a new terminal window:

```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies (if first time)
npm install

# Start Vite React Dev Server
npm run dev
```
- **React Web App**: [http://localhost:5173](http://localhost:5173)

---

## How to Use

1. Open **[http://localhost:5173](http://localhost:5173)** in your browser.
2. Ensure status indicator shows **🟢 Neo4j Connected**.
3. In the sidebar, enter your target repository path (e.g. `test_repo`) and click **⚡ Index Repository**.
4. Ask multi-hop questions about the codebase:
   - *"What does user_service.py do?"*
   - *"What exceptions does it raise?"* (Conversational memory resolves *"it"* automatically!).
   - *"What functions call repository.save?"*

---

## Project Structure

```
codebase_graphrag/
├── ingestion/         # tree-sitter multi-language parser (Python, TypeScript)
├── graph/             # Neo4j schema, batch loader, Cypher query library
├── embeddings/        # node text representation + qwen3 embedding generator
├── retrieval/         # hybrid Graph RAG retriever (vector search + graph traversal)
├── agent/             # LangGraph multi-node reasoning workflows
├── interface/         # FastAPI backend server (api.py)
├── frontend/          # React + Tailwind CSS dark-theme frontend
├── test_repo/         # hand-crafted FastAPI + TS Task Manager app (ground truth)
├── data/              # parsed.json, local chat sessions
├── docker-compose.yml # containerized Neo4j stack
├── requirements.txt   # Python dependencies
└── README.md
```
