from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_addon_store, get_repository
from app.core.auth import require_api_key
from app.db.repository import Repository
from app.models.schemas import (
    AddonCatalogResponse,
    AddonDescriptor,
    AddonInstallRequest,
    AddonInstallResponse,
)
from app.services.addon_store import AddonStore

router = APIRouter(prefix="/v1/addons", tags=["addons"], dependencies=[Depends(require_api_key)])


@router.get("/catalog", response_model=AddonCatalogResponse)
def list_catalog(
    repository: Repository = Depends(get_repository),
    addon_store: AddonStore = Depends(get_addon_store),
) -> AddonCatalogResponse:
    installed = repository.list_installed_addons()
    descriptors: list[AddonDescriptor] = []
    for spec in addon_store.catalog():
        descriptors.append(addon_store.as_descriptor(spec, installed=spec.id in installed))
    return AddonCatalogResponse(addons=descriptors)


@router.get("/installed", response_model=list[AddonInstallResponse])
def list_installed(repository: Repository = Depends(get_repository)) -> list[AddonInstallResponse]:
    installed = repository.list_installed_addons()
    return [
        AddonInstallResponse(addon_id=addon_id, installed=True, installed_at=installed_at)
        for addon_id, installed_at in installed.items()
    ]


@router.post("/install", response_model=AddonInstallResponse)
def install_addon(
    payload: AddonInstallRequest,
    repository: Repository = Depends(get_repository),
    addon_store: AddonStore = Depends(get_addon_store),
) -> AddonInstallResponse:
    if not addon_store.exists(payload.addon_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown addon id")
    installed_at = repository.install_addon(payload.addon_id)
    return AddonInstallResponse(addon_id=payload.addon_id, installed=True, installed_at=installed_at)


@router.post("/uninstall", response_model=AddonInstallResponse)
def uninstall_addon(
    payload: AddonInstallRequest,
    repository: Repository = Depends(get_repository),
) -> AddonInstallResponse:
    repository.uninstall_addon(payload.addon_id)
    return AddonInstallResponse(addon_id=payload.addon_id, installed=False, installed_at=None)
