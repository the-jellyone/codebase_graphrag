"""
Golden Benchmark Dataset for test_repo.

Contains 15 curated Q&A evaluation pairs with exact ground truth relationships,
entities, and expected answer facts derived directly from test_repo.
"""

from typing import List
from pydantic import BaseModel, Field


class GoldenQAPair(BaseModel):
    id: str
    category: str  # "impact_analysis" | "exception_flow" | "config_dependency" | "call_chain" | "structural_preset"
    question: str
    ground_truth: str
    expected_entities: List[str]  # Key function/class/config/exception names that MUST be present
    hops: int = 1


GOLDEN_BENCHMARK_DATASET: List[GoldenQAPair] = [
    # 1. Multi-Hop Impact Analysis
    GoldenQAPair(
        id="eval_01",
        category="impact_analysis",
        question="If I modify repository.save, what services and API routes are directly or indirectly impacted?",
        ground_truth=(
            "Direct callers of repository.save are user_service.create_user and task_service.create_task. "
            "Indirect callers (API routes) are routes.create_user and routes.create_task. "
            "It raises DatabaseException and reads config.DB_URL."
        ),
        expected_entities=["user_service.create_user", "task_service.create_task", "routes.create_user", "routes.create_task", "DatabaseException", "DB_URL"],
        hops=3,
    ),
    GoldenQAPair(
        id="eval_02",
        category="impact_analysis",
        question="What functions break or need updating if user_service.get_user is modified?",
        ground_truth=(
            "Direct callers of user_service.get_user are routes.get_user and task_service.create_task. "
            "Downstream, it calls repository.find_by_id."
        ),
        expected_entities=["routes.get_user", "task_service.create_task", "repository.find_by_id"],
        hops=2,
    ),

    # 2. Exception Flow & Propagation
    GoldenQAPair(
        id="eval_03",
        category="exception_flow",
        question="What exceptions can be raised during the execution of routes.create_user?",
        ground_truth=(
            "routes.create_user calls user_service.create_user, which calls validators.validate_email "
            "(raising ValidationException) and repository.save (raising DatabaseException)."
        ),
        expected_entities=["ValidationException", "DatabaseException", "validate_email", "save"],
        hops=2,
    ),

    # 3. Config & Environment Dependencies
    GoldenQAPair(
        id="eval_04",
        category="config_dependency",
        question="Which functions in the codebase read config.DB_URL?",
        ground_truth="repository.save reads config.DB_URL for database connection configuration.",
        expected_entities=["repository.save", "DB_URL"],
        hops=1,
    ),

    # 4. Multi-Hop Call Chains
    GoldenQAPair(
        id="eval_05",
        category="call_chain",
        question="Does task_service.create_task depend on user_service? Trace the full call chain.",
        ground_truth=(
            "Yes, task_service.create_task calls user_service.get_user to verify user existence, "
            "which in turn calls repository.find_by_id."
        ),
        expected_entities=["task_service.create_task", "user_service.get_user", "repository.find_by_id"],
        hops=2,
    ),

    # 5. Full Architecture Flow
    GoldenQAPair(
        id="eval_06",
        category="call_chain",
        question="What is the complete validation and persistence workflow when creating a new user?",
        ground_truth=(
            "routes.create_user receives the request, delegates to user_service.create_user, "
            "which validates input with validators.validate_email (raising ValidationException if invalid) "
            "and persists via repository.save (reading config.DB_URL and raising DatabaseException on failure)."
        ),
        expected_entities=["create_user", "validate_email", "save", "DB_URL"],
        hops=2,
    ),
]
