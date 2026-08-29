# CodeGraph 🕸️
A 100% local, fully offline **Codebase Intelligence & Graph RAG Engine**.

CodeGraph parses multi-language codebases (Python, JavaScript, React JSX, TypeScript) using Tree-sitter AST, constructs a Knowledge Graph in Neo4j, and uses local Ollama models with a 3-node LangGraph agent to answer complex multi-hop code questions.

---

## 📌 Why Use CodeGraph?

- **AST-Backed Graph vs. Flat Text:** Rather than breaking code into arbitrary text chunks, CodeGraph indexes code hierarchy (`CONTAINS`), function calls (`CALLS`), module dependencies (`IMPORTS`), and class methods (`HAS_METHOD`).
- **Multi-Hop Relational Reasoning:** Traces full call chains and executes impact analysis (*"what breaks if I change X?"*).
- **100% Offline & Private:** Runs entirely on `localhost` via Ollama and Dockerized Neo4j. Zero code or queries leave your machine.
- **Isolated Multi-Repo Management:** Index multiple codebases with composite `repo_id` partitioning so graphs never collide.
- **Incremental Syncing:** Only re-parses and updates files that were added or modified (via SHA-256 hash checks).

---

## 🤖 Models Used

Configured in `config.py`:

| Role | Default Model | Pull Command | Notes |
| :--- | :--- | :--- | :--- |
| **LLM / Agent** | `granite4.1:3b` (or `llama3.2`) | `ollama pull granite4.1:3b` | Fast local reasoning and synthesis |
| **Embeddings** | `qwen3-embedding:0.6b` | `ollama pull qwen3-embedding:0.6b` | Native Neo4j vector search embeddings |

*(You can also use `qwen2.5-coder:7b` or `bge-large` by setting `OLLAMA_LLM_MODEL` / `OLLAMA_EMBED_MODEL` in `.env`)*.

---

## 📋 Requirements

- **Python 3.10+**
- **Node.js 18+**
- **Docker** (for Neo4j 5.x)
- **Ollama** (running locally on port 11434)

---

## 🚀 How to Run

### 1. Start Neo4j
```bash
docker compose up -d neo4j
```
- **Neo4j Browser:** [http://localhost:7474](http://localhost:7474) (Credentials: `neo4j` / `password`)

### 2. Pull Ollama Models
```bash
ollama pull granite4.1:3b
ollama pull qwen3-embedding:0.6b
```

### 3. Start Backend
```bash
# Setup virtual environment and dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run FastAPI server
python -m interface.api
```
- Server runs at: [http://localhost:8000](http://localhost:8000)

### 4. Start Frontend
```bash
cd frontend
npm install
npm run dev
```
- Web UI runs at: [http://localhost:5173](http://localhost:5173)

---

## 💡 How to Use the App

1. Open **[http://localhost:5173](http://localhost:5173)**.
2. Click **`+ Add Repository`** in the sidebar → use the folder browser or click a preset (e.g. `test_repo`) → click **Add & Ingest**.
3. Choose your mode:
   - **Graph RAG:** Fast 1-hop vector search + subgraph context.
   - **Agent:** 3-node LangGraph loop with step-by-step reasoning trace drawer.
4. Click **View KG** to view live node/edge counts, resync changes, or copy ready-to-run Cypher queries for Neo4j Browser.

---

## 🧪 Evaluation

Run the automated RAGAS benchmark:
```bash
python -m evaluation.ragas_eval
```

