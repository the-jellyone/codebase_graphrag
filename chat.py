"""
Interactive Terminal CLI for Codebase GraphRAG.

Features:
- Live streaming answers with Markdown syntax highlighting
- Visual graph inspection (seed nodes + call hierarchy)
- Fast local inference powered by Ollama (qwen3:4b) + Neo4j
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.getLogger("neo4j").setLevel(logging.ERROR)

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.live import Live


from client import get_llm, EMBEDDING_MODEL, LLM_MODEL
from retrieval.retriever import CodeGraphRetriever

console = Console()

SYSTEM_PROMPT = """You are an expert codebase AI assistant. You answer technical questions about this repository using the provided CODEBASE CONTEXT extracted from an AST Knowledge Graph.

Instructions:
1. Ground your answers strictly in the provided code entities and graph relationships.
2. Always cite exact file paths and line numbers when referencing code (e.g. `backend/services/user_service.py:9`).
3. Explain the architectural flow (e.g. who calls what, exceptions raised, inheritance) using the graph metadata.
4. If something is not present in the context, state that clearly instead of guessing.
"""


def render_graph_inspection(seeds: list[dict], subgraph: dict) -> None:
    """Render a compact Rich table showing the retrieved graph seeds and call chains."""
    if not seeds:
        return

    table = Table(title="🔍 Retrieved Graph Subgraph", show_header=True, header_style="bold cyan", border_style="dim")
    table.add_column("Type", style="magenta", width=10)
    table.add_column("Entity Name", style="bold green")
    table.add_column("File Location", style="yellow")
    table.add_column("Score", justify="right", style="cyan")

    for s in seeds:
        score = f"{s.get('score', 0):.2f}" if "score" in s else "-"
        loc = f"{s.get('file', '')}:{s.get('line', '')}"
        table.add_row(s.get("type", "Node"), s.get("name", ""), loc, score)

    console.print(table)


def chat_loop():
    console.clear()
    console.rule("[bold cyan]Codebase GraphRAG Interactive CLI[/bold cyan]")
    console.print(f"[dim]LLM Model:[/dim] [green]{LLM_MODEL}[/green] | [dim]Embedding:[/dim] [cyan]{EMBEDDING_MODEL}[/cyan]")
    console.print("[dim]Type your question below. Type 'exit', 'quit', or 'q' to stop.[/dim]\n")

    retriever = CodeGraphRetriever()
    stream_llm = get_llm()

    while True:
        try:
            console.print("[bold yellow]Question > [/bold yellow]", end="")
            user_input = input().strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                console.print("\n[bold cyan]Goodbye![/bold cyan]")
                break

            if user_input.lower() == "clear":
                console.clear()
                continue

            # 1. Retrieve Graph Context
            with console.status("[bold green]Querying Knowledge Graph & Vectors...[/bold green]", spinner="dots"):
                retrieval_res = retriever.retrieve(user_input, top_k=4)

            # 2. Display Retrieved Subgraph Info
            render_graph_inspection(retrieval_res["seeds"], retrieval_res["subgraph"])

            # 3. Construct Final Prompt
            prompt = f"{retrieval_res['context']}\n\n[USER QUESTION]\n{user_input}\n\n[ANSWER]"

            # 4. Stream LLM Response
            console.print("\n[bold cyan]Answer:[/bold cyan]")
            response_text = ""
            
            for token in stream_llm(prompt, system_prompt=SYSTEM_PROMPT):
                response_text += token
                print(token, end="", flush=True)

            print("\n")
            console.print("[dim]─" * 60 + "[/dim]\n")

        except KeyboardInterrupt:
            console.print("\n[bold cyan]Interrupted. Type 'exit' to quit.[/bold cyan]\n")
        except Exception as exc:
            console.print(f"\n[bold red]Error:[/bold red] {exc}\n")


if __name__ == "__main__":
    chat_loop()
