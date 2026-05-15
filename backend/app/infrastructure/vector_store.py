from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.services.embeddings import cosine_similarity


class VectorStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VectorSearchResult:
    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        raise NotImplementedError


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            self._records[record.id] = record

    def search(
        self,
        query_vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        results: list[VectorSearchResult] = []
        for record in self._records.values():
            if not _matches_filters(record.payload, filters):
                continue
            results.append(
                VectorSearchResult(
                    id=record.id,
                    score=cosine_similarity(query_vector, record.vector),
                    payload=record.payload,
                )
            )
        return sorted(results, key=lambda result: result.score, reverse=True)[:limit]

    def delete(self, ids: list[str]) -> None:
        for vector_id in ids:
            self._records.pop(vector_id, None)

    def clear(self) -> None:
        self._records.clear()


class QdrantVectorStore(VectorStore):
    def __init__(self, base_url: str, collection: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.api_key = api_key

    def upsert(self, records: list[VectorRecord]) -> None:
        points = [
            {"id": record.id, "vector": record.vector, "payload": record.payload}
            for record in records
        ]
        self._request("PUT", f"/collections/{self.collection}/points", {"points": points})

    def search(
        self,
        query_vector: list[float],
        limit: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorSearchResult]:
        payload: dict[str, Any] = {"vector": query_vector, "limit": limit, "with_payload": True}
        if filters:
            payload["filter"] = {
                "must": [
                    {"key": key, "match": {"value": value}} for key, value in filters.items()
                ]
            }
        body = self._request("POST", f"/collections/{self.collection}/points/search", payload)
        raw_results = body.get("result")
        if not isinstance(raw_results, list):
            raise VectorStoreError("Qdrant returned an invalid search response.")
        results: list[VectorSearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict) or "id" not in item or "score" not in item:
                continue
            result_payload = item.get("payload")
            results.append(
                VectorSearchResult(
                    id=str(item["id"]),
                    score=float(item["score"]),
                    payload=result_payload if isinstance(result_payload, dict) else {},
                )
            )
        return results

    def delete(self, ids: list[str]) -> None:
        self._request(
            "POST",
            f"/collections/{self.collection}/points/delete",
            {"points": ids},
        )

    def _request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{urllib.parse.quote(path, safe='/')}",
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise VectorStoreError(f"Qdrant request failed: {exc}") from exc
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise VectorStoreError("Qdrant returned an invalid JSON response.")
        return parsed

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers


def _matches_filters(payload: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    return all(payload.get(key) == value for key, value in filters.items())
