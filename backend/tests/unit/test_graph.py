"""Unit tests for the property graph."""

import pytest

from app.engine.graph import GraphEdge, GraphNode, PropertyGraph
from app.engine.parser import CodeEntity, ParsedFile


def make_entity(name: str, file: str, line: int, calls: list[str] | None = None) -> CodeEntity:
    return CodeEntity(
        name=name,
        kind="function",
        file_path=file,
        start_line=line,
        end_line=line + 5,
        signature=f"def {name}()",
        calls=calls or [],
        code_text=f"def {name}(): pass",
    )


def make_parsed_file(file: str, entities: list[CodeEntity]) -> ParsedFile:
    return ParsedFile(
        file_path=file,
        language="python",
        entities=entities,
        imports=[],
        exports=[],
        total_lines=100,
    )


class TestGraphBuild:
    """The build() method should correctly wire up nodes, edges, and indices."""

    def test_empty_graph_has_no_nodes(self):
        g = PropertyGraph()
        g.build([], [])
        assert g.node_count() == 0
        assert g.edge_count() == 0

    def test_adds_one_node_per_entity(self):
        g = PropertyGraph()
        entities = [
            make_entity("foo", "a.py", 1),
            make_entity("bar", "a.py", 10),
        ]
        g.build(entities, [make_parsed_file("a.py", entities)])
        assert g.node_count() == 2
        assert g.edge_count() == 0  # no calls

    def test_creates_calls_edge(self):
        g = PropertyGraph()
        entities = [
            make_entity("caller", "a.py", 1, calls=["callee"]),
            make_entity("callee", "b.py", 1),
        ]
        g.build(entities, [])
        # 1 CALLS edge from caller -> callee
        call_edges = [e for e in g.edges if e.relation == "CALLS"]
        assert len(call_edges) == 1
        assert call_edges[0].source.startswith("a.py:caller")
        assert call_edges[0].target.startswith("b.py:callee")

    def test_no_self_edge(self):
        g = PropertyGraph()
        entities = [make_entity("foo", "a.py", 1, calls=["foo"])]
        g.build(entities, [])
        assert g.edge_count() == 0  # self-references are skipped

    def test_callers_of_resolves_to_caller_name(self):
        g = PropertyGraph()
        entities = [
            make_entity("do_thing", "main.py", 1, calls=["target"]),
            make_entity("target", "lib.py", 1),
        ]
        g.build(entities, [])
        callers = g.callers_of("target")
        assert "do_thing" in callers


class TestBlastRadius:
    """blast_radius should return external callers of nodes within a file."""

    def test_empty_file_returns_empty(self):
        g = PropertyGraph()
        g.build([], [])
        assert g.blast_radius("nonexistent.py") == []

    def test_external_caller_is_in_blast_radius(self):
        g = PropertyGraph()
        entities = [
            make_entity("process", "core.py", 1),
            make_entity("handler", "api.py", 1, calls=["process"]),
        ]
        g.build(entities, [])
        affected = g.blast_radius("core.py")
        assert len(affected) == 1
        assert affected[0]["caller"] == "handler"
        assert affected[0]["caller_file"] == "api.py"
        assert affected[0]["called"] == "process"

    def test_intra_file_caller_excluded(self):
        """Callers WITHIN the same file should NOT appear in blast radius."""
        g = PropertyGraph()
        entities = [
            make_entity("helper", "core.py", 1, calls=["process"]),
            make_entity("process", "core.py", 10),
        ]
        g.build(entities, [])
        affected = g.blast_radius("core.py")
        assert affected == []

    def test_unrelated_callers_excluded(self):
        """Callers of OTHER functions (not in the file) should not appear."""
        g = PropertyGraph()
        entities = [
            make_entity("unrelated", "api.py", 1, calls=["something_else"]),
            make_entity("something_else", "lib.py", 1),
            make_entity("process", "core.py", 1),
        ]
        g.build(entities, [])
        affected = g.blast_radius("core.py")
        assert affected == []


class TestCentrality:
    """high_centrality_nodes and top_callers should return the right ranking."""

    def test_high_centrality_nodes_orders_by_incoming(self):
        g = PropertyGraph()
        # 'target' is called by 3 distinct functions -> highest in-degree
        entities = [
            make_entity("target", "core.py", 1),
            make_entity("a_caller", "a.py", 1, calls=["target"]),
            make_entity("b_caller", "b.py", 1, calls=["target"]),
            make_entity("c_caller", "c.py", 1, calls=["target"]),
            make_entity("ignored", "x.py", 1),  # never called
        ]
        g.build(entities, [])
        top = g.high_centrality_nodes(n=10)
        # 'target' should be the top entry
        assert top[0]["name"] == "target"
        assert top[0]["incoming_calls"] == 3
        # 'ignored' should not appear (incoming = 0)
        names = [n["name"] for n in top]
        assert "ignored" not in names

    def test_high_centrality_respects_n(self):
        g = PropertyGraph()
        entities = [
            make_entity("target", "core.py", 1),
            make_entity("a", "a.py", 1, calls=["target"]),
            make_entity("b", "b.py", 1, calls=["target"]),
        ]
        g.build(entities, [])
        top = g.high_centrality_nodes(n=1)
        assert len(top) == 1

    def test_top_callers_orders_by_outgoing(self):
        g = PropertyGraph()
        entities = [
            make_entity("orchestrator", "main.py", 1, calls=["a", "b", "c"]),
            make_entity("a", "a.py", 1),
            make_entity("b", "b.py", 1),
            make_entity("c", "c.py", 1),
            make_entity("leaf", "leaf.py", 1),  # calls nothing
        ]
        g.build(entities, [])
        top = g.top_callers(n=10)
        assert top[0]["name"] == "orchestrator"
        assert top[0]["outgoing_calls"] == 3
        names = [n["name"] for n in top]
        assert "leaf" not in names

    def test_to_dict_includes_centrality(self):
        g = PropertyGraph()
        entities = [
            make_entity("target", "core.py", 1),
            make_entity("a", "a.py", 1, calls=["target"]),
        ]
        g.build(entities, [])
        d = g.to_dict()
        assert "node_count" in d
        assert "edge_count" in d
        assert "top_modules" in d
        assert "high_centrality_nodes" in d
        assert d["node_count"] == 2
        assert d["edge_count"] == 1
