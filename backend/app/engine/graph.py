"""Property graph for code entities.

For the MVP, the graph is held in-memory during indexing and persisted
to the Repository model's `graph_summary` JSONB field. For very large
codebases, swap the storage layer for FalkorDB or Neo4j — the public
methods (`build`, `blast_radius`, `callers_of`, `node_count`) are
intentionally small and replaceable.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from app.engine.parser import CodeEntity, ParsedFile


@dataclass
class GraphNode:
    id: str
    name: str
    kind: str
    file_path: str
    properties: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str  # CALLS, IMPLEMENTS, IMPORTS, CONTAINS, TESTS


class PropertyGraph:
    """Lightweight in-memory property graph optimized for code relationships."""

    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        # Fast lookup indices
        self._file_to_nodes: dict[str, list[str]] = defaultdict(list)
        self._name_to_nodes: dict[str, list[str]] = defaultdict(list)
        self._callers: dict[str, set[str]] = defaultdict(set)

    # ─── Construction ─────────────────────────────────────────

    def build(self, entities: list[CodeEntity], parsed_files: list[ParsedFile]) -> None:
        """Build the full graph from parsed entities."""
        # Add nodes
        for entity in entities:
            node_id = f"{entity.file_path}:{entity.name}:{entity.start_line}"
            node = GraphNode(
                id=node_id,
                name=entity.name,
                kind=entity.kind,
                file_path=entity.file_path,
                properties={
                    "start_line": entity.start_line,
                    "end_line": entity.end_line,
                    "signature": entity.signature,
                    "parent": entity.parent_name,
                    "decorators": entity.decorators,
                },
            )
            self.nodes[node_id] = node
            self._file_to_nodes[entity.file_path].append(node_id)
            self._name_to_nodes[entity.name].append(node_id)

        # Add CALLS edges
        for entity in entities:
            source_id = f"{entity.file_path}:{entity.name}:{entity.start_line}"
            for callee in entity.calls:
                target_ids = self._name_to_nodes.get(callee, [])
                for target_id in target_ids:
                    if target_id != source_id:
                        self.edges.append(
                            GraphEdge(source=source_id, target=target_id, relation="CALLS")
                        )
                        target_node = self.nodes.get(target_id)
                        if target_node:
                            self._callers[target_node.name].add(entity.name)

        # Add CONTAINS edges (parent -> child for classes)
        for entity in entities:
            if entity.parent_name:
                source_id = f"{entity.file_path}:{entity.name}:{entity.start_line}"
                parent_ids = [
                    nid
                    for nid in self._name_to_nodes.get(entity.parent_name, [])
                    if self.nodes[nid].file_path == entity.file_path
                ]
                for parent_id in parent_ids:
                    self.edges.append(
                        GraphEdge(source=parent_id, target=source_id, relation="CONTAINS")
                    )

    # ─── Queries ──────────────────────────────────────────────

    def blast_radius(self, file_path: str) -> list[dict]:
        """Find all nodes outside this file that call into nodes within this file."""
        affected: list[dict] = []
        file_nodes = self._file_to_nodes.get(file_path, [])
        file_node_names = {self.nodes[nid].name for nid in file_nodes}

        for edge in self.edges:
            if edge.relation != "CALLS" or edge.source in file_nodes:
                continue
            target_node = self.nodes.get(edge.target)
            if not target_node or target_node.name not in file_node_names:
                continue
            source_node = self.nodes.get(edge.source)
            if source_node:
                affected.append(
                    {
                        "caller": source_node.name,
                        "caller_file": source_node.file_path,
                        "called": target_node.name,
                        "called_file": target_node.file_path,
                    }
                )

        return affected

    def callers_of(self, function_name: str) -> list[str]:
        """Get all caller function names for a given function."""
        return list(self._callers.get(function_name, []))

    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    # ─── Serialization ────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize graph summary for database storage."""
        return {
            "node_count": self.node_count(),
            "edge_count": self.edge_count(),
            "top_modules": self._top_modules(10),
            "high_centrality_nodes": self._high_centrality_nodes(20),
        }

    def _top_modules(self, n: int) -> list[dict]:
        module_counts: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            module = node.file_path.split("/")[0] if "/" in node.file_path else "root"
            module_counts[module] += 1
        return sorted(
            [{"module": k, "entity_count": v} for k, v in module_counts.items()],
            key=lambda x: x["entity_count"],
            reverse=True,
        )[:n]

    def _high_centrality_nodes(self, n: int) -> list[dict]:
        """Nodes with the highest number of incoming CALLS edges (most important code)."""
        in_degree: dict[str, int] = defaultdict(int)
        for edge in self.edges:
            if edge.relation == "CALLS":
                in_degree[edge.target] += 1
        top = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:n]
        return [
            {
                "node_id": node_id,
                "name": self.nodes[node_id].name if node_id in self.nodes else "unknown",
                "file_path": self.nodes[node_id].file_path if node_id in self.nodes else "",
                "incoming_calls": count,
            }
            for node_id, count in top
        ]
