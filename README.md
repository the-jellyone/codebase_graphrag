# Codebase Graph RAG

A local, fully offline system that ingests code repositories, builds a knowledge graph in Neo4j, generates embeddings with ChromaDB, and performs Graph RAG via LangGraph agents to answer complex, multi-hop questions across codebases.

## Project Structure

```
codebase_graphrag/
├── ingestion/         # parser — ast + tree-sitter, gitpython
├── graph/             # neo4j loader, schema, cypher queries, update logic
├── embeddings/        # node → text → embed → chromadb
├── retrieval/         # graph rag — vector search + graph traversal + serialisation
├── agent/             # langgraph — planner, retriever, reasoner nodes
├── evaluation/        # eval dataset (json) + ragas scoring
├── interface/         # cli (typer) + streamlit UI
├── logs/              # stage-by-stage output logs
├── data/              # parsed.json, chroma db, cloned repos
├── tests/             # test suite per module
├── .env.example       # template environment variables
├── requirements.txt   # python dependencies
└── README.md
```

## Quick Start

### Option A: Running with Docker Compose (Recommended)

To run the entire system (Neo4j + Application + Streamlit UI) in Docker:

```bash
# 1. Clone repo & navigate into it
git clone <YOUR_REPO_URL>
cd codebase_graphrag

# 2. Configure environment (optional, defaults in compose work out-of-the-box)
cp .env.example .env

# 3. Start all services
docker compose up --build
```
- **Streamlit Web UI**: [http://localhost:8501](http://localhost:8501)
- **Neo4j Browser**: [http://localhost:7474](http://localhost:7474)

*(Note: Ensure Ollama is running on your host machine with `ollama serve` and models pulled).*

---

### Option B: Running Locally with Python Virtualenv

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env

# 4. Start local Neo4j (if not using docker-compose)
docker run \
    --name codebase_neo4j \
    --publish=7474:7474 --publish=7687:7687 \
    --env NEO4J_AUTH=neo4j/password \
    neo4j:5.20-community
```
