"""
Tests for ingestion/parser.py against the ground-truth test_repo.

Each test asserts that a specific edge or node from design_test_repo.md
is present in the ParseResult. This makes the test repo self-contained:
the code AND the answer key are in the same place.

Run with:
  pytest tests/test_parser.py -v
"""

from pathlib import Path
import pytest

from ingestion.parser import parse_repo
from ingestion.models import ParseResult, EdgeType, NodeType


# Absolute path to the test repo (relative to project root)
TEST_REPO = Path(__file__).parent.parent / "test_repo"


@pytest.fixture(scope="module")
def parsed() -> ParseResult:
    """Parse the test_repo once for all tests in this module."""
    return parse_repo(TEST_REPO)


# -------------------------------------------------------------------------
# Helper
# -------------------------------------------------------------------------

def has_edge(result: ParseResult, source_contains: str, target_contains: str, edge_type: str) -> bool:
    """Return True if any edge matches the given source/target substrings and type."""
    for edge in result.edges:
        if (
            source_contains in edge.source
            and target_contains in edge.target
            and edge.type == edge_type
        ):
            return True
    return False


def has_node(result: ParseResult, name: str, node_type: str) -> bool:
    return any(n.name == name and n.type == node_type for n in result.nodes)


# -------------------------------------------------------------------------
# Node existence tests
# -------------------------------------------------------------------------

class TestNodes:
    def test_module_nodes_extracted(self, parsed):
        assert any(n.type == NodeType.MODULE for n in parsed.nodes), \
            "No Module nodes extracted"

    def test_user_class_extracted(self, parsed):
        assert has_node(parsed, "User", NodeType.CLASS), "User class not found"

    def test_task_class_extracted(self, parsed):
        assert has_node(parsed, "Task", NodeType.CLASS), "Task class not found"

    def test_base_model_class_extracted(self, parsed):
        assert has_node(parsed, "BaseModel", NodeType.CLASS), "BaseModel class not found"

    def test_create_user_function(self, parsed):
        assert has_node(parsed, "create_user", NodeType.FUNCTION), \
            "create_user function not found"

    def test_create_task_function(self, parsed):
        assert has_node(parsed, "create_task", NodeType.FUNCTION), \
            "create_task function not found"

    def test_exception_nodes_extracted(self, parsed):
        exc_names = {n.name for n in parsed.nodes if n.type == NodeType.EXCEPTION}
        assert "NotFoundException" in exc_names, "NotFoundException not extracted"
        assert "DatabaseException" in exc_names, "DatabaseException not extracted"
        assert "ValidationException" in exc_names, "ValidationException not extracted"


# -------------------------------------------------------------------------
# INHERITS edge tests
# -------------------------------------------------------------------------

class TestInherits:
    def test_user_inherits_base_model(self, parsed):
        assert has_edge(parsed, "user.py::User", "BaseModel", EdgeType.INHERITS), \
            "INHERITS: User → BaseModel missing"

    def test_task_inherits_base_model(self, parsed):
        assert has_edge(parsed, "task.py::Task", "BaseModel", EdgeType.INHERITS), \
            "INHERITS: Task → BaseModel missing"


# -------------------------------------------------------------------------
# IMPORTS edge tests
# -------------------------------------------------------------------------

class TestImports:
    def test_routes_imports_user_service(self, parsed):
        assert has_edge(parsed, "routes.py", "user_service.py", EdgeType.IMPORTS), \
            "IMPORTS: routes → user_service missing"

    def test_routes_imports_task_service(self, parsed):
        assert has_edge(parsed, "routes.py", "task_service.py", EdgeType.IMPORTS), \
            "IMPORTS: routes → task_service missing"

    def test_task_service_imports_user_service(self, parsed):
        assert has_edge(parsed, "task_service.py", "user_service.py", EdgeType.IMPORTS), \
            "IMPORTS: task_service → user_service missing (cross-service)"

    def test_repository_imports_config(self, parsed):
        assert has_edge(parsed, "repository.py", "config.py", EdgeType.IMPORTS), \
            "IMPORTS: repository → config missing"

    def test_user_model_imports_base(self, parsed):
        assert has_edge(parsed, "user.py", "base.py", EdgeType.IMPORTS), \
            "IMPORTS: user.py → base.py missing"

    def test_task_model_imports_base(self, parsed):
        assert has_edge(parsed, "task.py", "base.py", EdgeType.IMPORTS), \
            "IMPORTS: task.py → base.py missing"


# -------------------------------------------------------------------------
# CALLS edge tests
# -------------------------------------------------------------------------

class TestCalls:
    def test_routes_create_user_calls_service(self, parsed):
        assert has_edge(parsed, "routes.py::create_user", "user_service", EdgeType.CALLS), \
            "CALLS: routes.create_user → user_service.create_user missing"

    def test_routes_create_task_calls_service(self, parsed):
        assert has_edge(parsed, "routes.py::create_task", "task_service", EdgeType.CALLS), \
            "CALLS: routes.create_task → task_service.create_task missing"

    def test_user_service_create_user_calls_repository_save(self, parsed):
        assert has_edge(parsed, "user_service.py::create_user", "repository", EdgeType.CALLS), \
            "CALLS: user_service.create_user → repository.save missing"

    def test_user_service_create_user_calls_validate_email(self, parsed):
        assert has_edge(parsed, "user_service.py::create_user", "validators", EdgeType.CALLS), \
            "CALLS: user_service.create_user → validators.validate_email missing"

    def test_task_service_calls_user_service_get_user(self, parsed):
        assert has_edge(parsed, "task_service.py::create_task", "user_service", EdgeType.CALLS), \
            "CALLS: task_service.create_task → user_service.get_user missing (cross-service)"


# -------------------------------------------------------------------------
# RAISES edge tests
# -------------------------------------------------------------------------

class TestRaises:
    def test_find_by_id_raises_not_found(self, parsed):
        assert has_edge(parsed, "find_by_id", "NotFoundException", EdgeType.RAISES), \
            "RAISES: repository.find_by_id → NotFoundException missing"

    def test_save_raises_database_exception(self, parsed):
        assert has_edge(parsed, "save", "DatabaseException", EdgeType.RAISES), \
            "RAISES: repository.save → DatabaseException missing"

    def test_validate_email_raises_validation_exception(self, parsed):
        assert has_edge(parsed, "validate_email", "ValidationException", EdgeType.RAISES), \
            "RAISES: validators.validate_email → ValidationException missing"


# -------------------------------------------------------------------------
# READS (config) edge tests
# -------------------------------------------------------------------------

class TestReads:
    def test_save_reads_db_url(self, parsed):
        assert has_edge(parsed, "save", "config.DB_URL", EdgeType.READS), \
            "READS: repository.save → config.DB_URL missing"

    def test_find_by_id_reads_max_connections(self, parsed):
        assert has_edge(parsed, "find_by_id", "config.MAX_CONNECTIONS", EdgeType.READS), \
            "READS: repository.find_by_id → config.MAX_CONNECTIONS missing"


# -------------------------------------------------------------------------
# TypeScript extraction tests
# -------------------------------------------------------------------------

class TestTypeScript:
    def test_typescript_interfaces_extracted(self, parsed):
        assert has_node(parsed, "User", NodeType.CLASS), "TS interface User not found"
        assert has_node(parsed, "Task", NodeType.CLASS), "TS interface Task not found"

    def test_typescript_functions_extracted(self, parsed):
        assert has_node(parsed, "getUser", NodeType.FUNCTION), "TS function getUser not found"
        assert has_node(parsed, "createUser", NodeType.FUNCTION), "TS function createUser not found"

    def test_typescript_user_service_calls_client(self, parsed):
        assert has_edge(parsed, "userService.ts::getUser", "client", EdgeType.CALLS), \
            "CALLS: TS userService.getUser → client.get missing"

