from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import cast
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.infrastructure.file_storage import LocalFileStorage
from app.infrastructure.models import (
    Document,
    DocumentChunk,
    DocumentFile,
    DocumentVersion,
    TaskJob,
    Workspace,
)
from app.schemas.documents import DocumentContentUpdateRequest
from app.services.document_parsers import DocumentParserRouter, ParsedDocument


class DocumentService:
    def __init__(
        self,
        session: Session,
        storage: LocalFileStorage,
        parser_router: DocumentParserRouter | None = None,
    ) -> None:
        self.session = session
        self.storage = storage
        self.parser_router = parser_router or DocumentParserRouter()

    def import_file(
        self,
        workspace_id: str,
        original_name: str,
        content: bytes,
        mime_type: str | None,
    ) -> tuple[Document | None, DocumentFile | None, TaskJob, bool]:
        task_job = self._create_task_job(
            workspace_id=workspace_id,
            job_type="document_import_file",
            target_type="document",
            input_={"original_name": original_name, "mime_type": mime_type},
        )
        self._ensure_workspace(workspace_id)

        try:
            file_hash = sha256(content).hexdigest()
            duplicate_file = self._find_document_file_by_hash(workspace_id, file_hash)
            if duplicate_file is not None:
                document = self._find_document_by_file_id(duplicate_file.id)
                self._complete_task(task_job, document, duplicate=True)
                self.session.commit()
                return document, duplicate_file, task_job, True

            file_id = _new_id("file")
            stored = self.storage.save(workspace_id, file_id, original_name, content)
            document_file = DocumentFile(
                id=file_id,
                workspace_id=workspace_id,
                original_name=original_name,
                storage_backend=stored.storage_backend,
                storage_path=stored.storage_path,
                mime_type=mime_type,
                file_size=stored.file_size,
                sha256=file_hash,
            )
            self.session.add(document_file)

            parsed = self.parser_router.parse(Path(stored.storage_path), original_name)
            document = self._create_document_from_parsed(
                workspace_id=workspace_id,
                parsed=parsed,
                source_type="file",
                source_uri=original_name,
                file_id=document_file.id,
                content_type=mime_type,
                content_hash=file_hash,
            )
            self._complete_task(task_job, document, duplicate=False)
            self.session.commit()
            return document, document_file, task_job, False
        except Exception as exc:
            self._fail_task(task_job, exc)
            self.session.commit()
            return None, None, task_job, False

    def import_url(
        self,
        workspace_id: str,
        url: str,
        title: str | None,
    ) -> tuple[Document | None, TaskJob]:
        task_job = self._create_task_job(
            workspace_id=workspace_id,
            job_type="document_import_url",
            target_type="document",
            input_={"url": url, "title": title},
        )
        self._ensure_workspace(workspace_id)

        try:
            text = _fetch_url_text(url)
            parsed = ParsedDocument(
                title=title or url,
                content_md=text,
                content_text=text,
                metadata={"source_url": url},
            )
            document = self._create_document_from_parsed(
                workspace_id=workspace_id,
                parsed=parsed,
                source_type="url",
                source_uri=url,
                file_id=None,
                content_type="text/plain",
                content_hash=sha256(text.encode("utf-8")).hexdigest(),
            )
            self._complete_task(task_job, document, duplicate=False)
            self.session.commit()
            return document, task_job
        except Exception as exc:
            self._fail_task(task_job, exc)
            self.session.commit()
            return None, task_job

    def list_documents(self, workspace_id: str | None = None) -> list[Document]:
        statement = select(Document).order_by(Document.updated_at.desc())
        if workspace_id is not None:
            statement = statement.where(Document.workspace_id == workspace_id)
        return list(self.session.scalars(statement))

    def get_document(self, doc_id: str) -> Document:
        document = self.session.get(Document, doc_id)
        if document is None:
            raise AppError("not_found", "Document not found.", status_code=404)
        return document

    def get_version(self, doc_id: str, version_id: str) -> DocumentVersion:
        statement = select(DocumentVersion).where(
            DocumentVersion.doc_id == doc_id,
            DocumentVersion.id == version_id,
        )
        version = self.session.scalar(statement)
        if version is None:
            raise AppError("not_found", "Document version not found.", status_code=404)
        return version

    def save_content(
        self,
        doc_id: str,
        request: DocumentContentUpdateRequest,
    ) -> tuple[DocumentVersion, int]:
        document = self.get_document(doc_id)
        content_text = request.content_md
        next_version_no = self._next_version_no(doc_id)
        version = DocumentVersion(
            id=_new_id("ver"),
            doc_id=doc_id,
            version_no=next_version_no,
            title=request.title or document.title,
            content_md=request.content_md,
            content_text=content_text,
            change_summary=request.change_summary,
            content_hash=sha256(request.content_md.encode("utf-8")).hexdigest(),
            created_by=request.created_by,
        )
        self.session.add(version)
        document.title = request.title or document.title
        document.content_hash = version.content_hash
        document.metadata_ = {
            **(document.metadata_ or {}),
            "current_version_id": version.id,
        }
        self.session.flush()
        chunk_count = self._replace_chunks(document, version, content_text)
        self.session.commit()
        return version, chunk_count

    def _create_document_from_parsed(
        self,
        workspace_id: str,
        parsed: ParsedDocument,
        source_type: str,
        source_uri: str,
        file_id: str | None,
        content_type: str | None,
        content_hash: str,
    ) -> Document:
        document = Document(
            id=_new_id("doc"),
            workspace_id=workspace_id,
            title=parsed.title,
            source_type=source_type,
            source_uri=source_uri,
            file_id=file_id,
            content_type=content_type,
            status="ready",
            parse_status="completed",
            content_hash=content_hash,
            metadata_=parsed.metadata,
        )
        self.session.add(document)
        self.session.flush()

        version = DocumentVersion(
            id=_new_id("ver"),
            doc_id=document.id,
            version_no=1,
            title=parsed.title,
            content_md=parsed.content_md,
            content_text=parsed.content_text,
            content_hash=content_hash,
            change_summary="Initial import",
        )
        self.session.add(version)
        self.session.flush()
        chunk_count = self._replace_chunks(document, version, parsed.content_text)
        document.metadata_ = {
            **parsed.metadata,
            "current_version_id": version.id,
            "chunk_count": chunk_count,
        }
        return document

    def _replace_chunks(
        self,
        document: Document,
        version: DocumentVersion,
        content_text: str,
    ) -> int:
        self.session.execute(delete(DocumentChunk).where(DocumentChunk.version_id == version.id))
        chunks = split_document_chunks(content_text)
        for chunk in chunks:
            self.session.add(
                DocumentChunk(
                    id=_new_id("chunk"),
                    doc_id=document.id,
                    version_id=version.id,
                    chunk_index=chunk.index,
                    heading=chunk.heading,
                    content=chunk.content,
                    content_hash=sha256(chunk.content.encode("utf-8")).hexdigest(),
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    token_count=len(chunk.content.split()),
                    metadata_={},
                )
            )
        return len(chunks)

    def _create_task_job(
        self,
        workspace_id: str,
        job_type: str,
        target_type: str,
        input_: dict[str, str | None],
    ) -> TaskJob:
        task_job = TaskJob(
            id=_new_id("job"),
            workspace_id=workspace_id,
            job_type=job_type,
            target_type=target_type,
            status="running",
            progress=0,
            input=input_,
            output={},
        )
        self.session.add(task_job)
        self.session.flush()
        return task_job

    def _complete_task(self, task_job: TaskJob, document: Document | None, duplicate: bool) -> None:
        task_job.status = "completed"
        task_job.progress = 100
        if document is not None:
            task_job.target_id = document.id
        task_job.output = {
            "document_id": document.id if document else None,
            "duplicate": duplicate,
        }

    def _fail_task(self, task_job: TaskJob, exc: Exception) -> None:
        task_job.status = "failed"
        task_job.progress = 100
        task_job.error_message = str(exc)
        task_job.output = {"error": str(exc)}

    def _ensure_workspace(self, workspace_id: str) -> None:
        if self.session.get(Workspace, workspace_id) is None:
            self.session.add(Workspace(id=workspace_id, name=workspace_id))
            self.session.flush()

    def _find_document_file_by_hash(self, workspace_id: str, file_hash: str) -> DocumentFile | None:
        statement = select(DocumentFile).where(
            DocumentFile.workspace_id == workspace_id,
            DocumentFile.sha256 == file_hash,
        )
        return self.session.scalar(statement)

    def _find_document_by_file_id(self, file_id: str) -> Document | None:
        return self.session.scalar(select(Document).where(Document.file_id == file_id))

    def _next_version_no(self, doc_id: str) -> int:
        statement = select(func.max(DocumentVersion.version_no)).where(
            DocumentVersion.doc_id == doc_id
        )
        current = self.session.scalar(statement)
        return int(current or 0) + 1


class Chunk:
    def __init__(
        self,
        index: int,
        content: str,
        start_offset: int,
        end_offset: int,
        heading: str | None = None,
    ) -> None:
        self.index = index
        self.content = content
        self.start_offset = start_offset
        self.end_offset = end_offset
        self.heading = heading


def split_document_chunks(content: str, max_chars: int = 900) -> list[Chunk]:
    normalized = content.strip()
    if not normalized:
        return [Chunk(index=0, content="", start_offset=0, end_offset=0)]

    chunks: list[Chunk] = []
    start = 0
    for index, piece in enumerate(_split_text(normalized, max_chars)):
        offset = content.find(piece, start)
        if offset < 0:
            offset = start
        heading = _chunk_heading(piece)
        chunks.append(
            Chunk(
                index=index,
                content=piece,
                start_offset=offset,
                end_offset=offset + len(piece),
                heading=heading,
            )
        )
        start = offset + len(piece)
    return chunks


def _split_text(text: str, max_chars: int) -> Sequence[str]:
    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not current:
            current = paragraph
        elif len(current) + len(paragraph) + 2 <= max_chars:
            current = f"{current}\n\n{paragraph}"
        else:
            chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _chunk_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or None
    return None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _fetch_url_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "KnowPilot/0.1"})
    with urlopen(request, timeout=10) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        text = response.read().decode(content_type, errors="replace")
        return cast(str, text)
