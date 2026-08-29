# CodeGraph 🕸️
### Local, Zero-Data-Leakage Codebase GraphRAG & Multi-Hop Autonomous Agent

**CodeGraph** transforms full-stack codebases (Python, JavaScript, React JSX, TypeScript) into **AST-derived Knowledge Graphs in Neo4j**, enabling high-accuracy **Hybrid GraphRAG** and **Autonomous Multi-Hop Relational Reasoning** via LangGraph.

The entire engine runs **100% locally and offline** using local Ollama models and self-hosted Neo4j — zero code leaves your machine.

---

## 🌟 Why CodeGraph? (GraphRAG vs. Traditional RAG)

Traditional Code RAG models treat code like flat text, slicing files into arbitrary 500-token chunks. This breaks semantic structure:
- ❌ **Lost Call Hierarchies:** Cannot trace multi-hop function calls across files (`A -> B -> C`).
- ❌ **No Impact Analysis:** Cannot reliably determine *"what breaks if I change function X?"*.
- ❌ **Hallucinations on Dependencies:** Misses class method encapsulation, inheritance, and module imports.

### How CodeGraph Solves This:
- 🌲 **Tree-sitter AST Parsing:** Accurately extracts Functions, Classes, React JSX Components, Module imports, and Call expressions.
- 🕸️ **Neo4j Code Topology:** Stores symbols as interconnected nodes with `CALLS`, `CONTAINS`, `IMPORTS`, and `HAS_METHOD` relationships.
- ⚡ **Hybrid GraphRAG:** Direct dense vector search + 2-hop subgraph context extraction for fast, targeted answers.
- 🤖 **3-Node LangGraph Agent:** An autonomous cycle (*Orchestrator → Executor → Synthesizer*) that traces call chains, executes Cypher queries, and checks for knowledge gaps before answering.

---

## 🎯 Key Features

- **Polyglot Full-Stack AST Parsing:** Ingests Python (`.py`), JavaScript (`.js`, `.mjs`, `.cjs`), React JSX (`.jsx`), and TypeScript (`.ts`, `.tsx`).
- **Dual Query Modes:**
  - **Graph RAG Mode (Fast):** 1-hop vector search + multi-hop graph subgraph context.
  - **Agent Mode (Autonomous):** 3-node LangGraph loop with step-by-step reasoning trace drawer.
- **Isolated Multi-Repo Partitioning:** Index multiple repositories in the same database without cross-repo data contamination (isolated via composite `repo_id`).
- **Incremental File Syncing:** Hashes files with SHA-256 and only re-parses modified or added files.
- **Single-Click Repo Cleanup:** Deleting a repository wipes all its graph nodes from Neo4j (`DETACH DELETE`) and cascades SQLite chat cleanup.
- **Interactive Knowledge Graph Hub:** Top status card (live nodes, edges, sync status) + 6 ready-to-run repo-scoped Cypher queries + 1-click **Launch in Neo4j Browser**.
- **Native OS Folder Picker:** Choose directories directly through your native OS file dialog (`webkitdirectory`), drag-and-drop zone, or quick project presets.
- **Real-Time Streaming:** Server-Sent Events (SSE) token streaming for zero perceived latency.

---

## 🧠 Recommended Local Models (Ollama)

CodeGraph integrates seamlessly with [Ollama](https://ollama.ai). Below are recommended model pairings:

| Model Type | Recommended Model | Size | Pull Command | Description |
| :--- | :--- | :--- | :--- | :--- |
| **LLM (Best Overall)** | `qwen2.5-coder:7b` | 4.7 GB | `ollama pull qwen2.5-coder:7b` | Outstanding code reasoning, AST tool execution, and synthesis. |
| **LLM (Lightweight / Fast)** | `llama3.2:3b` | 2.0 GB | `ollama pull llama3.2` | Fast responses on standard laptops. |
| **LLM (Deep Reasoning)** | `deepseek-coder-v2:16b` | 8.9 GB | `ollama pull deepseek-coder-v2:16b` | Enterprise-grade multi-hop architecture analysis. |
| **Embedding Model** | `bge-large` | 1.3 GB | `ollama pull bge-large` | High semantic search accuracy across code docstrings & names. |
| **Embedding Model (Alternative)** | `nomic-embed-text` | 274 MB | `ollama pull nomic-embed-text` | Ultra-fast lightweight embeddings. |

> Configure your preferred models in `config.py` (`OLLAMA_LLM_MODEL` and `OLLAMA_EMBED_MODEL`).

---

## 📋 System Requirements & Prerequisites

1. **Docker Desktop**: For running the Neo4j 5.x graph database.
2. **Python 3.10+**: For backend API and parsing pipeline.
3. **Node.js 18+**: For Vite React frontend.
4. **Ollama**: Running locally with your chosen LLM and embedding model.

---

## 🚀 Quickstart Guide

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/your-username/codebase_graphrag.git
cd codebase_graphrag

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

---

### 2. Start Neo4j via Docker

```bash
docker compose up -d neo4j
```
- **Neo4j Browser**: [http://localhost:7474](http://localhost:7474) (Credentials: `neo4j` / `password`)

---

### 3. Start Local Ollama Models

```bash
ollama run qwen2.5-coder:7b
ollama pull bge-large
```

---

### 4. Start FastAPI Backend

```bash
# From repository root (with venv activated)
python -m interface.api
```
- **Backend API**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### 5. Start React Frontend

In a new terminal window:

```bash
cd frontend
npm install
npm run dev
```
- **Web Interface**: [http://localhost:5173](http://localhost:5173)

---

## 💡 How to Use

1. Open **[http://localhost:5173](http://localhost:5173)** in your browser.
2. Click **`+ Add Repository`** in the sidebar:
   - Click **"Click to Browse Folder from Disk"** to select a project folder from your computer.
   - Or click one of the quick suggestion chips (e.g. `test_repo`).
3. Click **Add & Ingest**. The background indexing tracker will discover files, run Tree-sitter AST parsing, generate embeddings, and construct the Neo4j graph.
4. Select your mode (**Graph RAG** or **Agent**) and ask questions:
   - *"What is this repository about and what are its main services?"*
   - *"Trace the complete call chain starting from user login."*
   - *"What breaks if I change `classify_allergens` in the backend?"*
   - *"Which React components render the allergen cards in the frontend?"*
5. Click **View KG** on the top right to inspect live nodes/edges and copy or run ready-to-use Cypher queries in Neo4j Browser.

---

## 📊 Evaluation & Benchmarking (RAGAS)

CodeGraph includes an automated evaluation pipeline measuring **Faithfulness**, **Answer Relevancy**, **Context Precision**, and **Context Recall** on multi-hop code reasoning:

```bash
python -m evaluation.ragas_eval
```

---

## 🔒 Privacy & Security Guarantee

- **100% Offline**: All models, embeddings, graph storage, and chat histories remain strictly on `localhost`.
- **Zero Telemetry**: No code, metadata, or queries are ever sent to external cloud APIs.
- **Enterprise-Ready**: Safe for private, proprietary, or regulated codebases.

---

## 📄 License

MIT License — free for personal, educational, and commercial use.
