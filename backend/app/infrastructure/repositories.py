from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import Document, Entity, EntityRelation, TaskJob, Workspace


class WorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, workspace: Workspace) -> Workspace:
        self.session.add(workspace)
        return workspace

    def get(self, workspace_id: str) -> Workspace | None:
        return self.session.get(Workspace, workspace_id)

    def list(self) -> list[Workspace]:
        return list(self.session.scalars(select(Workspace).order_by(Workspace.created_at.desc())))


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, document: Document) -> Document:
        self.session.add(document)
        return document

    def get(self, document_id: str) -> Document | None:
        return self.session.get(Document, document_id)

    def list_by_workspace(self, workspace_id: str) -> list[Document]:
        statement = select(Document).where(Document.workspace_id == workspace_id)
        return list(self.session.scalars(statement))


class EntityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: Entity) -> Entity:
        self.session.add(entity)
        return entity

    def get(self, entity_id: str) -> Entity | None:
        return self.session.get(Entity, entity_id)

    def find_by_normalized_name(self, workspace_id: str, normalized_name: str) -> Entity | None:
        statement = select(Entity).where(
            Entity.workspace_id == workspace_id,
            Entity.normalized_name == normalized_name,
        )
        return self.session.scalar(statement)


class RelationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, relation: EntityRelation) -> EntityRelation:
        self.session.add(relation)
        return relation

    def list_by_source(self, source_entity_id: str) -> list[EntityRelation]:
        statement = select(EntityRelation).where(
            EntityRelation.source_entity_id == source_entity_id
        )
        return list(self.session.scalars(statement))


class TaskJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, task_job: TaskJob) -> TaskJob:
        self.session.add(task_job)
        return task_job

    def get(self, task_job_id: str) -> TaskJob | None:
        return self.session.get(TaskJob, task_job_id)

    def list_by_status(self, status: str) -> list[TaskJob]:
        statement = select(TaskJob).where(TaskJob.status == status)
        return list(self.session.scalars(statement))
