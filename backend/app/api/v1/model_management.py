# ruff: noqa: B008

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db_session
from app.schemas.model_management import (
    ConnectionTestResponse,
    ModelCreate,
    ModelResponse,
    ModelRouteResponse,
    ModelRouteUpdate,
    ModelUpdate,
    ProviderCreate,
    ProviderResponse,
    ProviderTestRequest,
    ProviderUpdate,
)
from app.services.model_connection_test import ModelConnectionTester
from app.services.model_management import ModelManagementService

router = APIRouter(prefix="/model-management", tags=["model-management"])


def get_model_management_service(
    session: Session = Depends(get_db_session),
) -> ModelManagementService:
    return ModelManagementService(session)


@router.get("/providers", response_model=list[ProviderResponse])
def list_providers(
    service: ModelManagementService = Depends(get_model_management_service),
) -> list[ProviderResponse]:
    return service.list_providers()


@router.post("/providers", response_model=ProviderResponse, status_code=201)
def create_provider(
    payload: ProviderCreate, service: ModelManagementService = Depends(get_model_management_service)
) -> ProviderResponse:
    return service.create_provider(payload)


@router.post("/providers/test", response_model=ConnectionTestResponse)
def test_provider(payload: ProviderTestRequest) -> ConnectionTestResponse:
    return ModelConnectionTester().test(payload)


@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
def update_provider(
    provider_id: str,
    payload: ProviderUpdate,
    service: ModelManagementService = Depends(get_model_management_service),
) -> ProviderResponse:
    return service.update_provider(provider_id, payload)


@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(
    provider_id: str, service: ModelManagementService = Depends(get_model_management_service)
) -> Response:
    service.delete_provider(provider_id)
    return Response(status_code=204)


@router.get("/models", response_model=list[ModelResponse])
def list_models(
    service: ModelManagementService = Depends(get_model_management_service),
) -> list[ModelResponse]:
    return service.list_models()


@router.post("/models", response_model=ModelResponse, status_code=201)
def create_model(
    payload: ModelCreate, service: ModelManagementService = Depends(get_model_management_service)
) -> ModelResponse:
    return service.create_model(payload)


@router.patch("/models/{model_id}", response_model=ModelResponse)
def update_model(
    model_id: str,
    payload: ModelUpdate,
    service: ModelManagementService = Depends(get_model_management_service),
) -> ModelResponse:
    return service.update_model(model_id, payload)


@router.delete("/models/{model_id}", status_code=204)
def delete_model(
    model_id: str, service: ModelManagementService = Depends(get_model_management_service)
) -> Response:
    service.delete_model(model_id)
    return Response(status_code=204)


@router.get("/routes", response_model=list[ModelRouteResponse])
def list_routes(
    service: ModelManagementService = Depends(get_model_management_service),
) -> list[ModelRouteResponse]:
    return service.list_routes()


@router.put("/routes/{capability}", response_model=ModelRouteResponse)
def set_route(
    capability: str,
    payload: ModelRouteUpdate,
    service: ModelManagementService = Depends(get_model_management_service),
) -> ModelRouteResponse:
    return service.set_route(capability, payload.model_config_id)
