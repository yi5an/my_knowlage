from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.services.research_agent import ResearchAgentService
from app.services.structured_output import (
    MockStructuredOutputClient,
    OpenAICompatibleStructuredOutputClient,
    StructuredOutputClient,
)
from app.services.web_search import (
    MockWebSearchClient,
    WebSearchClient,
    build_web_search_client_from_settings,
)

DB_SESSION_DEPENDENCY = Depends(get_db_session)

# The deep-research workflow produces richer JSON than summaries do (multi-claim
# lists, a full structured report), so it gets a larger output budget and one
# extra retry. These reduce the chance a long response is truncated mid-JSON,
# which is the most common real-LLM failure mode we hit end-to-end.
RESEARCH_LLM_MAX_OUTPUT_TOKENS = 4096
RESEARCH_LLM_RETRIES = 3


def build_llm_client_from_settings() -> StructuredOutputClient:
    """Build a structured-output LLM client from settings.

    Mirrors ``services/youtube/summary.build_summary_service_from_settings``:
    a real OpenAI-compatible client when ``LLM_API_KEY`` is configured, else a
    mock client for no-key local mode (tests / offline development).
    """
    settings = get_settings()
    api_key = settings.llm_api_key
    if api_key:
        return OpenAICompatibleStructuredOutputClient(
            api_key=api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            # Research output is richer than summaries; favour a larger budget
            # over the global default so reports/claims don't get truncated.
            max_output_tokens=max(
                settings.llm_max_output_tokens, RESEARCH_LLM_MAX_OUTPUT_TOKENS
            ),
            retries=RESEARCH_LLM_RETRIES,
        )
    return MockStructuredOutputClient()


def build_web_client_from_settings() -> WebSearchClient:
    """Build a web search client from settings, with a mock fallback.

    In production a Tavily key must be set. For local development without a
    key we fall back to ``MockWebSearchClient`` so the API still responds;
    tests inject their own client and never hit this path.
    """
    settings = get_settings()
    if settings.tavily_api_key:
        return build_web_search_client_from_settings(settings)
    return MockWebSearchClient()


def get_research_agent_service(session: Session = DB_SESSION_DEPENDENCY) -> ResearchAgentService:
    return ResearchAgentService(
        session=session,
        llm_client=build_llm_client_from_settings(),
        web_search_client=build_web_client_from_settings(),
    )
