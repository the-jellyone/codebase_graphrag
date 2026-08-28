"""Evaluation package: dataset management, evaluation pipelines, and quantitative benchmark metrics."""

from evaluation.dataset import GOLDEN_BENCHMARK_DATASET, GoldenQAPair
from evaluation.evaluator import (
    calculate_entity_metrics,
    calculate_entity_recall,
    calculate_token_overlap,
    evaluate_deterministic,
    evaluate_llm_judge,
)
from evaluation.benchmark import run_full_benchmark

__all__ = [
    "GOLDEN_BENCHMARK_DATASET",
    "GoldenQAPair",
    "calculate_entity_metrics",
    "calculate_entity_recall",
    "calculate_token_overlap",
    "evaluate_deterministic",
    "evaluate_llm_judge",
    "run_full_benchmark",
]
