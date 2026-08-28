"""
Benchmark Runner: Single-Shot Graph RAG vs 3-Node LangGraph Agent.

Executes all 15 Golden Evaluation Pairs against both systems, calculates
quantitative metrics, and produces a comprehensive markdown comparison report.

Usage:
    python -m evaluation.benchmark
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List

import ollama
from loguru import logger

from config import OLLAMA_LLM_MODEL, OLLAMA_EMBED_MODEL
from graph.connection import get_driver
from retrieval.retriever import retrieve_subgraph_context
from agent import run_agent
from evaluation.dataset import GOLDEN_BENCHMARK_DATASET, GoldenQAPair
from evaluation.evaluator import evaluate_deterministic

RESULTS_DIR = Path("evaluation/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def run_single_shot_rag(question: str) -> tuple[str, float]:
    """Execute single-shot Graph RAG pipeline and measure wall time."""
    start_t = time.perf_counter()
    driver = get_driver()
    
    context_str, _, _ = retrieve_subgraph_context(
        query_text=question,
        driver=driver,
        embed_model=OLLAMA_EMBED_MODEL,
    )
    
    prompt = (
        f"You are a code intelligence assistant. Use this graph context to answer the question:\n\n"
        f"{context_str}\n\n"
        f"Question: {question}"
    )
    
    res = ollama.chat(
        model=OLLAMA_LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        think=False,
        options={"temperature": 0.0},
    )
    
    elapsed = time.perf_counter() - start_t
    return res["message"]["content"].strip(), elapsed


def run_agent_evaluation(question: str) -> tuple[str, float]:
    """Execute 3-Node LangGraph Agent and measure wall time."""
    start_t = time.perf_counter()
    answer = run_agent(question)
    elapsed = time.perf_counter() - start_t
    return answer, elapsed


def run_full_benchmark(dataset: List[GoldenQAPair] = GOLDEN_BENCHMARK_DATASET) -> Dict[str, Any]:
    """Run full benchmark across all dataset pairs with 100% deterministic scoring."""
    logger.info(f"Starting deterministic benchmark across {len(dataset)} Golden Q&A Pairs...")
    
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": OLLAMA_LLM_MODEL,
        "single_shot": [],
        "agent": [],
        "summary": {},
    }
    
    ss_recalls, ss_precisions, ss_f1s, ss_overlaps, ss_times = [], [], [], [], []
    ag_recalls, ag_precisions, ag_f1s, ag_overlaps, ag_times = [], [], [], [], []
    
    for idx, item in enumerate(dataset, 1):
        logger.info(f"[{idx}/{len(dataset)}] Evaluating {item.id} ({item.category})...")
        
        # 1. Single-Shot RAG
        ss_answer, ss_time = run_single_shot_rag(item.question)
        ss_metrics = evaluate_deterministic(item.question, item.ground_truth, ss_answer, item.expected_entities)
        
        ss_recalls.append(ss_metrics["recall"])
        ss_precisions.append(ss_metrics["precision"])
        ss_f1s.append(ss_metrics["f1"])
        ss_overlaps.append(ss_metrics["fact_overlap"])
        ss_times.append(ss_time)
        
        results["single_shot"].append({
            "id": item.id,
            "category": item.category,
            "question": item.question,
            "answer": ss_answer,
            "recall": ss_metrics["recall"],
            "precision": ss_metrics["precision"],
            "f1": ss_metrics["f1"],
            "fact_overlap": ss_metrics["fact_overlap"],
            "time_seconds": round(ss_time, 2),
        })
        
        # 2. 3-Node LangGraph Agent
        ag_answer, ag_time = run_agent_evaluation(item.question)
        ag_metrics = evaluate_deterministic(item.question, item.ground_truth, ag_answer, item.expected_entities)
        
        ag_recalls.append(ag_metrics["recall"])
        ag_precisions.append(ag_metrics["precision"])
        ag_f1s.append(ag_metrics["f1"])
        ag_overlaps.append(ag_metrics["fact_overlap"])
        ag_times.append(ag_time)
        
        results["agent"].append({
            "id": item.id,
            "category": item.category,
            "question": item.question,
            "answer": ag_answer,
            "recall": ag_metrics["recall"],
            "precision": ag_metrics["precision"],
            "f1": ag_metrics["f1"],
            "fact_overlap": ag_metrics["fact_overlap"],
            "time_seconds": round(ag_time, 2),
        })

    # Summary aggregations
    results["summary"] = {
        "total_queries": len(dataset),
        "single_shot": {
            "avg_recall": round(sum(ss_recalls) / len(ss_recalls), 3),
            "avg_precision": round(sum(ss_precisions) / len(ss_precisions), 3),
            "avg_f1": round(sum(ss_f1s) / len(ss_f1s), 3),
            "avg_fact_overlap": round(sum(ss_overlaps) / len(ss_overlaps), 3),
            "avg_latency_s": round(sum(ss_times) / len(ss_times), 2),
        },
        "agent": {
            "avg_recall": round(sum(ag_recalls) / len(ag_recalls), 3),
            "avg_precision": round(sum(ag_precisions) / len(ag_precisions), 3),
            "avg_f1": round(sum(ag_f1s) / len(ag_f1s), 3),
            "avg_fact_overlap": round(sum(ag_overlaps) / len(ag_overlaps), 3),
            "avg_latency_s": round(sum(ag_times) / len(ag_times), 2),
        },
    }

    # Save JSON results
    with open(RESULTS_DIR / "benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
        
    # Generate Markdown Report
    _generate_markdown_report(results)
    
    logger.success("Deterministic Evaluation Benchmark complete! Results written to evaluation/results/")
    return results


def _generate_markdown_report(results: Dict[str, Any]) -> None:
    """Generate executive Markdown comparison table."""
    summary = results["summary"]
    ss_sum = summary["single_shot"]
    ag_sum = summary["agent"]
    
    md = [
        "# Codebase Graph RAG — Benchmark & Evaluation Report",
        f"**Date:** {results['timestamp']} | **Model:** `{results['model']}` | **Dataset:** 15 Golden Ground Truth Q&A Pairs\n",
        "## 1. Executive Summary Comparison\n",
        "| Metric | Single-Shot Graph RAG | 3-Node LangGraph Agent | Delta |",
        "|---|---|---|---|",
        f"| **Entity Recall** | {ss_sum['avg_recall'] * 100:.1f}% | **{ag_sum['avg_recall'] * 100:.1f}%** | {('+' if ag_sum['avg_recall'] >= ss_sum['avg_recall'] else '')}{round((ag_sum['avg_recall'] - ss_sum['avg_recall']) * 100, 1)}% |",
        f"| **Entity Precision** | {ss_sum['avg_precision'] * 100:.1f}% | **{ag_sum['avg_precision'] * 100:.1f}%** | {('+' if ag_sum['avg_precision'] >= ss_sum['avg_precision'] else '')}{round((ag_sum['avg_precision'] - ss_sum['avg_precision']) * 100, 1)}% |",
        f"| **Entity F1 Score** | {ss_sum['avg_f1'] * 100:.1f}% | **{ag_sum['avg_f1'] * 100:.1f}%** | {('+' if ag_sum['avg_f1'] >= ss_sum['avg_f1'] else '')}{round((ag_sum['avg_f1'] - ss_sum['avg_f1']) * 100, 1)}% |",
        f"| **Fact Overlap (Jaccard)** | {ss_sum['avg_fact_overlap'] * 100:.1f}% | **{ag_sum['avg_fact_overlap'] * 100:.1f}%** | {('+' if ag_sum['avg_fact_overlap'] >= ss_sum['avg_fact_overlap'] else '')}{round((ag_sum['avg_fact_overlap'] - ss_sum['avg_fact_overlap']) * 100, 1)}% |",
        f"| **Avg Latency** | {ss_sum['avg_latency_s']}s | {ag_sum['avg_latency_s']}s | - |",
        "\n---\n",
        "## 2. Detailed Per-Query Results\n",
        "| ID | Category | Question | Single-Shot Recall | Agent Recall | Delta |",
        "|---|---|---|---|---|---|",
    ]
    
    for ss, ag in zip(results["single_shot"], results["agent"]):
        delta_recall = ag["recall"] - ss["recall"]
        delta_str = f"+{delta_recall*100:.0f}%" if delta_recall > 0 else f"{delta_recall*100:.0f}%"
        md.append(f"| `{ss['id']}` | `{ss['category']}` | {ss['question']} | {ss['recall']*100:.0f}% | **{ag['recall']*100:.0f}%** | {delta_str} |")

    report_path = RESULTS_DIR / "benchmark_report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(md))


if __name__ == "__main__":
    run_full_benchmark()
