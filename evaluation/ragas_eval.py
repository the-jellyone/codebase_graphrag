"""
Official RAGAS Evaluation Pipeline.

Uses the `ragas` library with local Ollama models to compute:
- Faithfulness
- Answer Relevancy
- Context Precision
- Context Recall

Usage:
    python -m evaluation.ragas_eval
"""

import json
import time
from pathlib import Path
from typing import Dict, Any

from loguru import logger
from datasets import Dataset

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from langchain_ollama import OllamaLLM, OllamaEmbeddings

from config import OLLAMA_LLM_MODEL, OLLAMA_EMBED_MODEL, OLLAMA_BASE_URL
from graph.connection import get_driver
from retrieval.retriever import retrieve_subgraph_context
from agent import run_agent
from evaluation.dataset import GOLDEN_BENCHMARK_DATASET

RESULTS_DIR = Path("evaluation/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def build_ragas_dataset(use_agent: bool = False) -> Dataset:
    """Build HuggingFace Dataset required by RAGAS evaluate()."""
    driver = get_driver()
    data = {
        "question": [],
        "answer": [],
        "contexts": [],
        "ground_truth": [],
    }

    for item in GOLDEN_BENCHMARK_DATASET:
        logger.info(f"Preparing RAGAS samples for: {item.id}...")
        
        # Retrieve graph context
        context_str, _, _ = retrieve_subgraph_context(
            query_text=item.question,
            driver=driver,
            embed_model=OLLAMA_EMBED_MODEL,
        )
        
        # Generate Answer
        if use_agent:
            ans = run_agent(item.question)
        else:
            from evaluation.benchmark import run_single_shot_rag
            ans, _ = run_single_shot_rag(item.question)

        data["question"].append(item.question)
        data["answer"].append(ans)
        data["contexts"].append([context_str])
        data["ground_truth"].append(item.ground_truth)

    return Dataset.from_dict(data)


def run_ragas_evaluation() -> Dict[str, Any]:
    """Execute official RAGAS evaluation with local Ollama."""
    logger.info("Initializing RAGAS with local Ollama LLM and Embeddings...")

    llm = OllamaLLM(
        model=OLLAMA_LLM_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.0,
    )
    
    embeddings = OllamaEmbeddings(
        model=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    logger.info("Generating dataset samples...")
    eval_dataset = build_ragas_dataset(use_agent=True)

    logger.info("Computing RAGAS metrics (Faithfulness, Relevancy, Precision, Recall)...")
    results = evaluate(
        dataset=eval_dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=llm,
        embeddings=embeddings,
    )

    df = results.to_pandas()
    report_path = RESULTS_DIR / "ragas_report.csv"
    df.to_csv(report_path, index=False)
    
    logger.success(f"RAGAS evaluation complete! Results exported to {report_path}")
    print("\n" + "="*50 + "\nRAGAS EVALUATION SCORES:\n" + "="*50)
    print(results)
    return results


if __name__ == "__main__":
    run_ragas_evaluation()
