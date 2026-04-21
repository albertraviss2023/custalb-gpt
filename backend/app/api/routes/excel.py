from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import Response

from app.api.dependencies import get_excel_service
from app.core.auth import require_api_key
from app.models.excel_schemas import ExcelActionResponse, ExcelSessionMetadata, ExcelSetActiveSheetRequest
from app.services.excel_service import ExcelService

router = APIRouter(prefix="/v1/excel", tags=["excel"], dependencies=[Depends(require_api_key)])

@router.post("/sessions", response_model=ExcelSessionMetadata)
async def create_session(
    file: UploadFile = File(...),
    excel_service: ExcelService = Depends(get_excel_service)
) -> ExcelSessionMetadata:
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx and .xlsm files are supported")
    
    content = await file.read()
    session_id = excel_service.session_manager.create_session(file.filename, content)
    metadata = excel_service.get_metadata(session_id)
    if not metadata:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create session")
    return metadata

@router.get("/sessions/{session_id}", response_model=ExcelSessionMetadata)
def get_session(
    session_id: str,
    excel_service: ExcelService = Depends(get_excel_service)
) -> ExcelSessionMetadata:
    metadata = excel_service.get_metadata(session_id)
    if not metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return metadata

@router.post("/sessions/{session_id}/active-sheet")
def set_active_sheet(
    session_id: str,
    payload: ExcelSetActiveSheetRequest | None = Body(default=None),
    sheet_name: str | None = Query(default=None),
    excel_service: ExcelService = Depends(get_excel_service)
):
    resolved_sheet_name = payload.sheet_name if payload else sheet_name
    if not resolved_sheet_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sheet_name is required")
    excel_service.session_manager.set_active_sheet(session_id, resolved_sheet_name)
    return {"status": "ok", "active_sheet": resolved_sheet_name}

@router.post("/sessions/{session_id}/chat", response_model=ExcelActionResponse)
async def chat_action(
    session_id: str,
    user_instruction: str,
    model_id: Optional[str] = None,
    excel_service: ExcelService = Depends(get_excel_service)
) -> ExcelActionResponse:
    try:
        plan = await excel_service.plan_action(session_id, user_instruction, model_id)
        summary = excel_service.apply_action(session_id, plan)
        
        metadata = excel_service.get_metadata(session_id)
        preview = metadata.preview # Updated preview
        
        return ExcelActionResponse(
            session_id=session_id,
            summary=summary,
            changed_sheet=plan.sheet_name or metadata.active_sheet,
            preview=preview,
            action_plan=plan
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/sessions/{session_id}/download")
def download_workbook(
    session_id: str,
    excel_service: ExcelService = Depends(get_excel_service)
):
    try:
        content = excel_service.save_workbook(session_id)
        metadata = excel_service.get_metadata(session_id)
        filename = f"modified_{metadata.filename}"
        
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
