# Codebase Graph RAG — Benchmark & Evaluation Report
**Date:** 2026-08-29 00:03:19 | **Model:** `granite4.1:3b` | **Dataset:** 6 Golden Ground Truth Q&A Pairs

## 1. Executive Summary Comparison

| Metric | Single-Shot Graph RAG | 3-Node LangGraph Agent | Delta |
|---|---|---|---|
| **Entity Recall** | 19.4% | **43.1%** | +23.7% |
| **Entity Precision** | 58.3% | **50.0%** | -8.3% |
| **Entity F1 Score** | 26.1% | **36.8%** | +10.7% |
| **Fact Overlap (Jaccard)** | 4.2% | **11.0%** | +6.8% |
| **Avg Latency** | 8.69s | 30.38s | - |

---

## 2. Detailed Per-Query Results

| ID | Category | Question | Single-Shot Recall | Agent Recall | Delta |
|---|---|---|---|---|---|
| `eval_01` | `impact_analysis` | If I modify repository.save, what services and API routes are directly or indirectly impacted? | 0% | **100%** | +100% |
| `eval_02` | `impact_analysis` | What functions break or need updating if user_service.get_user is modified? | 33% | **67%** | +33% |
| `eval_03` | `exception_flow` | What exceptions can be raised during the execution of routes.create_user? | 0% | **0%** | 0% |
| `eval_04` | `config_dependency` | Which functions in the codebase read config.DB_URL? | 50% | **0%** | -50% |
| `eval_05` | `call_chain` | Does task_service.create_task depend on user_service? Trace the full call chain. | 33% | **67%** | +33% |
| `eval_06` | `call_chain` | What is the complete validation and persistence workflow when creating a new user? | 0% | **25%** | +25% |