"""
Integration tests for Neo4j Knowledge Graph and Cypher queries.

Tests:
1. Neo4j connectivity
2. Schema & Vector Index setup
3. Graph ingestion from parsed test_repo
4. Verification of ground-truth relationships directly via Cypher
5. Impact analysis & multi-hop call chain traversals

Run with:
  pytest tests/test_graph.py -v
"""

from pathlib import Path
import pytest

from ingestion.parser import parse_repo
from graph.connection import Neo4jConnection
from graph.schema import clear_database, setup_schema
from graph.loader import load_parsed_repo_into_graph
from graph.queries import get_call_chain, get_upstream_callers, get_impact_analysis

TEST_REPO = Path(__file__).parent.parent / "test_repo"


@pytest.fixture(scope="module")
def neo4j_conn():
    """Create a live connection to local Neo4j Docker container."""
    conn = Neo4jConnection()
    try:
        conn.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Local Neo4j is not reachable at {conn.uri}: {exc}")
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def loaded_graph(neo4j_conn):
    """Parse test_repo and load into Neo4j once for this test module."""
    driver = neo4j_conn.get_driver()
    clear_database(driver)
    
    # Parse repo
    parsed_result = parse_repo(TEST_REPO)
    
    # Load into Neo4j (without requiring active Ollama in CI/tests, using fallback dimension)
    load_parsed_repo_into_graph(
        parsed_result,
        driver=driver,
        generate_embeddings=False,
    )
    return parsed_result


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

class TestGraphLoading:
    def test_nodes_present_in_neo4j(self, neo4j_conn, loaded_graph):
        """Verify node counts in Neo4j match distinct parsed node IDs."""
        results = neo4j_conn.run_query("MATCH (n) RETURN count(n) AS total_nodes")
        distinct_node_ids = {n.id for n in loaded_graph.nodes}
        assert results[0]["total_nodes"] == len(distinct_node_ids)



    def test_user_service_calls_repository_in_neo4j(self, neo4j_conn, loaded_graph):
        """Verify CALLS edge in Neo4j: create_user -> save."""
        query = """
        MATCH (caller:Function)-[:CALLS]->(callee:Function)
        WHERE caller.name = 'create_user' AND callee.name = 'save'
        RETURN caller.id AS caller_id, callee.id AS callee_id
        """
        results = neo4j_conn.run_query(query)
        assert len(results) >= 1, "Expected CALLS edge from create_user to save in Neo4j"

    def test_inheritance_in_neo4j(self, neo4j_conn, loaded_graph):
        """Verify User -> BaseModel INHERITS edge in Neo4j."""
        query = """
        MATCH (child:Class)-[:INHERITS]->(parent:Class)
        WHERE child.name = 'User' AND parent.name = 'BaseModel'
        RETURN child.name, parent.name
        """
        results = neo4j_conn.run_query(query)
        assert len(results) >= 1, "Expected INHERITS edge from User to BaseModel in Neo4j"

    def test_raises_exceptions_in_neo4j(self, neo4j_conn, loaded_graph):
        """Verify RAISES edge: find_by_id -> NotFoundException."""
        query = """
        MATCH (f:Function)-[:RAISES]->(e:Exception)
        WHERE f.name = 'find_by_id' AND e.name = 'NotFoundException'
        RETURN f.name, e.name
        """
        results = neo4j_conn.run_query(query)
        assert len(results) >= 1, "Expected RAISES edge from find_by_id to NotFoundException in Neo4j"

    def test_reads_config_in_neo4j(self, neo4j_conn, loaded_graph):
        """Verify READS edge: save -> config.DB_URL."""
        query = """
        MATCH (f:Function)-[:READS]->(c:Config)
        WHERE f.name = 'save' AND c.name = 'config.DB_URL'
        RETURN f.name, c.name
        """
        results = neo4j_conn.run_query(query)
        assert len(results) >= 1, "Expected READS edge from save to config.DB_URL in Neo4j"


class TestGraphQueries:
    def test_multi_hop_call_chain(self, neo4j_conn, loaded_graph):
        """Test multi-hop call chain: routes.create_user -> user_service.create_user -> repository.save."""
        driver = neo4j_conn.get_driver()
        start_id = "backend/api/routes.py::create_user"
        chains = get_call_chain(driver, start_id, max_depth=3)
        assert len(chains) >= 1, f"Expected call chains originating from {start_id}"
        
        # Verify that 'save' is reached downstream
        found_save = any("save" in chain["call_chain"] for chain in chains)
        assert found_save, "Call chain did not reach repository.save"

    def test_impact_analysis_query(self, neo4j_conn, loaded_graph):
        """Test impact analysis for repository.save."""
        driver = neo4j_conn.get_driver()
        target_id = "backend/db/repository.py::save"
        impact = get_impact_analysis(driver, target_id)
        
        assert impact["target_name"] == "save"
        assert len(impact["upstream_callers"]) >= 2, "Expected multiple upstream callers for save"
        assert "config.DB_URL" in impact["configs_read"]
        assert "DatabaseException" in impact["exceptions_raised"]
