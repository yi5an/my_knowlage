from __future__ import annotations

from app.services.graph_dependencies import get_graph_store
from app.services.research_dependencies import build_llm_client_from_settings
from app.services.task_worker import TaskJobProcessor


def build_task_job_processor() -> TaskJobProcessor:
    """Assemble the task_job processor from settings.

    Shares the LLM client assembly with the research/extraction paths (real
    OpenAI-compatible client when ``LLM_API_KEY`` is set, else a mock) and the
    same graph store the graph API uses, so extracted entities land in the
    same in-memory/Kuzu graph that ``GET /graph`` reads from.
    """
    from app.infrastructure.database import SessionLocal

    return TaskJobProcessor(
        session_factory=SessionLocal,
        llm_client=build_llm_client_from_settings(),
        graph_store=get_graph_store(),
    )
