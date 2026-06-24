from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any


class GraphStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphStoreNode:
    id: str
    label: str
    node_type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphStoreEdge:
    id: str
    source_id: str
    target_id: str
    relation_type: str
    confidence: float | None = None
    evidence: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphSubgraph:
    nodes: list[GraphStoreNode]
    edges: list[GraphStoreEdge]


class GraphStore(ABC):
    @abstractmethod
    def upsert_nodes(self, nodes: list[GraphStoreNode]) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert_edges(self, edges: list[GraphStoreEdge]) -> None:
        raise NotImplementedError

    @abstractmethod
    def neighbors(
        self,
        node_id: str,
        depth: int,
        limit: int,
        node_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> GraphSubgraph:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        query: str,
        workspace_id: str,
        limit: int,
        node_types: list[str] | None = None,
    ) -> GraphSubgraph:
        raise NotImplementedError

    @abstractmethod
    def path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int,
    ) -> GraphSubgraph:
        raise NotImplementedError


class InMemoryGraphStore(GraphStore):
    def __init__(self) -> None:
        self.nodes: dict[str, GraphStoreNode] = {}
        self.edges: dict[str, GraphStoreEdge] = {}

    def upsert_nodes(self, nodes: list[GraphStoreNode]) -> None:
        for node in nodes:
            self.nodes[node.id] = node

    def upsert_edges(self, edges: list[GraphStoreEdge]) -> None:
        for edge in edges:
            self.edges[edge.id] = edge

    def neighbors(
        self,
        node_id: str,
        depth: int,
        limit: int,
        node_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> GraphSubgraph:
        if node_id not in self.nodes:
            return GraphSubgraph(nodes=[], edges=[])
        selected_nodes: dict[str, GraphStoreNode] = {node_id: self.nodes[node_id]}
        selected_edges: dict[str, GraphStoreEdge] = {}
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        visited_depth: dict[str, int] = {node_id: 0}
        while queue and len(selected_nodes) <= limit:
            current_id, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in self._incident_edges(current_id, relation_types, min_confidence):
                next_id = edge.target_id if edge.source_id == current_id else edge.source_id
                next_node = self.nodes.get(next_id)
                if next_node is None or not _node_type_allowed(next_node, node_types):
                    continue
                selected_edges[edge.id] = edge
                selected_nodes[next_id] = next_node
                next_depth = current_depth + 1
                if visited_depth.get(next_id, depth + 1) > next_depth:
                    visited_depth[next_id] = next_depth
                    queue.append((next_id, next_depth))
                if len(selected_nodes) >= limit:
                    break
        return GraphSubgraph(
            nodes=list(selected_nodes.values()),
            edges=list(selected_edges.values()),
        )

    def search(
        self,
        query: str,
        workspace_id: str,
        limit: int,
        node_types: list[str] | None = None,
    ) -> GraphSubgraph:
        # Treat "*" or empty query as a wildcard returning all nodes.
        wildcard = query.strip() in ("", "*")
        lowered = query.lower()
        results: list[GraphStoreNode] = []
        for node in self.nodes.values():
            if node.properties.get("workspace_id") != workspace_id:
                continue
            if not _node_type_allowed(node, node_types):
                continue
            if wildcard or lowered in node.label.lower() or lowered in str(node.properties).lower():
                results.append(node)
            if len(results) >= limit:
                break
        node_ids = {node.id for node in results}
        edges = [
            edge
            for edge in self.edges.values()
            if edge.source_id in node_ids and edge.target_id in node_ids
        ]
        return GraphSubgraph(nodes=results, edges=edges)

    def path(self, source_id: str, target_id: str, max_depth: int) -> GraphSubgraph:
        if source_id not in self.nodes or target_id not in self.nodes:
            return GraphSubgraph(nodes=[], edges=[])
        queue: deque[tuple[str, list[str], list[str]]] = deque([(source_id, [source_id], [])])
        visited = {source_id}
        while queue:
            current_id, node_path, edge_path = queue.popleft()
            if len(edge_path) >= max_depth:
                continue
            for edge in self._incident_edges(current_id, None, None):
                next_id = edge.target_id if edge.source_id == current_id else edge.source_id
                next_node_path = [*node_path, next_id]
                next_edge_path = [*edge_path, edge.id]
                if next_id == target_id:
                    return GraphSubgraph(
                        nodes=[self.nodes[node_id] for node_id in next_node_path],
                        edges=[self.edges[edge_id] for edge_id in next_edge_path],
                    )
                if next_id not in visited:
                    visited.add(next_id)
                    queue.append((next_id, next_node_path, next_edge_path))
        return GraphSubgraph(nodes=[], edges=[])

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()

    def _incident_edges(
        self,
        node_id: str,
        relation_types: list[str] | None,
        min_confidence: float | None,
    ) -> list[GraphStoreEdge]:
        results: list[GraphStoreEdge] = []
        for edge in self.edges.values():
            if edge.source_id != node_id and edge.target_id != node_id:
                continue
            if relation_types and edge.relation_type not in relation_types:
                continue
            if min_confidence is not None and (edge.confidence or 0) < min_confidence:
                continue
            results.append(edge)
        return results


class KuzuGraphStore(GraphStore):
    def __init__(self, database_path: str | None) -> None:
        if not database_path:
            raise GraphStoreError("KUZU_DATABASE_PATH is required for Kuzu graph store.")
        try:
            import kuzu  # type: ignore[import-not-found]
        except ImportError as exc:
            raise GraphStoreError("Kuzu graph store is not available: install kuzu first.") from exc
        self._kuzu = kuzu
        self.database_path = database_path

    def upsert_nodes(self, nodes: list[GraphStoreNode]) -> None:
        raise GraphStoreError("KuzuGraphStore adapter is configured but not initialized.")

    def upsert_edges(self, edges: list[GraphStoreEdge]) -> None:
        raise GraphStoreError("KuzuGraphStore adapter is configured but not initialized.")

    def neighbors(
        self,
        node_id: str,
        depth: int,
        limit: int,
        node_types: list[str] | None = None,
        relation_types: list[str] | None = None,
        min_confidence: float | None = None,
    ) -> GraphSubgraph:
        raise GraphStoreError("KuzuGraphStore adapter is configured but not initialized.")

    def search(
        self,
        query: str,
        workspace_id: str,
        limit: int,
        node_types: list[str] | None = None,
    ) -> GraphSubgraph:
        raise GraphStoreError("KuzuGraphStore adapter is configured but not initialized.")

    def path(self, source_id: str, target_id: str, max_depth: int) -> GraphSubgraph:
        raise GraphStoreError("KuzuGraphStore adapter is configured but not initialized.")


def _node_type_allowed(node: GraphStoreNode, node_types: list[str] | None) -> bool:
    return not node_types or node.node_type in node_types
