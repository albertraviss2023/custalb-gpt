from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_model_registry, get_vllm_client, get_repository
from app.core.auth import require_api_key
from app.db.repository import Repository
from app.models.schemas import ModelSelectionRequest, ModelSelectionResponse, ModelsResponse
from app.services.model_registry import ModelRegistry
from app.services.vllm_client import VLLMClient

router = APIRouter(prefix="/v1", tags=["models"], dependencies=[Depends(require_api_key)])


@router.get("/models", response_model=ModelsResponse)
async def list_models(
    repository: Repository = Depends(get_repository),
    model_registry: ModelRegistry = Depends(get_model_registry),
    vllm_client: VLLMClient = Depends(get_vllm_client),
) -> ModelsResponse:
    default_model_id = repository.get_default_model_id(model_registry.default_model_id)
    if not model_registry.exists(default_model_id):
        default_model_id = model_registry.default_model_id

    available_refs = await vllm_client.list_model_refs()
    availability: dict[str, bool] = {}
    for profile in model_registry.all_profiles():
        # vLLM refs are usually just the model name/path
        runtime_refs = [profile.runtime.model_ref, *profile.runtime.availability_refs]
        availability[profile.id] = any(ref in available_refs for ref in runtime_refs)

    return ModelsResponse(
        default_model_id=default_model_id,
        models=model_registry.list_descriptors(availability=availability),
    )


@router.get("/model-selection", response_model=ModelSelectionResponse)
def get_model_selection(
    repository: Repository = Depends(get_repository),
    model_registry: ModelRegistry = Depends(get_model_registry),
) -> ModelSelectionResponse:
    model_id = repository.get_default_model_id(model_registry.default_model_id)
    if not model_registry.exists(model_id):
        model_id = model_registry.default_model_id
    return ModelSelectionResponse(model_id=model_id)


@router.post("/model-selection", response_model=ModelSelectionResponse)
def set_model_selection(
    payload: ModelSelectionRequest,
    repository: Repository = Depends(get_repository),
    model_registry: ModelRegistry = Depends(get_model_registry),
) -> ModelSelectionResponse:
    if not model_registry.exists(payload.model_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown model id")

    repository.set_default_model_id(payload.model_id)
    return ModelSelectionResponse(model_id=payload.model_id)
