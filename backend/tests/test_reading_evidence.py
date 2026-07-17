from dataclasses import dataclass

from app.services.reading_evidence import ReadingEvidenceAdapter, ReadingEvidenceCandidate


@dataclass
class FakeSearchResult:
    chunk_id: str
    document_id: str
    title: str
    content: str
    score: float


@dataclass
class FakeSearchResponse:
    results: list[FakeSearchResult]


class FakeRagService:
    def search(self, _request: object) -> FakeSearchResponse:
        return FakeSearchResponse(
            results=[
                FakeSearchResult(
                    chunk_id="chunk_current",
                    document_id="doc_current",
                    title="Current",
                    content="GPU demand",
                    score=0.99,
                ),
                FakeSearchResult(
                    chunk_id="chunk_other",
                    document_id="doc_other",
                    title="Other",
                    content="Other evidence about GPU demand",
                    score=0.88,
                ),
            ]
        )


def test_evidence_adapter_excludes_the_current_chunk() -> None:
    adapter = ReadingEvidenceAdapter(session=None, rag_service=FakeRagService())

    candidates = adapter.search(
        workspace_id="ws_a",
        query="GPU demand",
        excluded_chunk_ids={"chunk_current"},
    )

    assert candidates == [
        ReadingEvidenceCandidate(
            source_kind="document",
            source_id="chunk_other",
            workspace_id="ws_a",
            document_id="doc_other",
            chunk_id="chunk_other",
            title="Other",
            excerpt="Other evidence about GPU demand",
            published_at=None,
            retrieval_score=0.88,
        )
    ]
