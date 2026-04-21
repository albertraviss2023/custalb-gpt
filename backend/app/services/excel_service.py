from __future__ import annotations

import io
import json
import uuid
import re
from typing import Any, Dict, Optional

import openpyxl
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.models.excel_schemas import ExcelActionPlan, ExcelSheetPreview, ExcelSessionMetadata
from app.services.vllm_client import InferenceError
from app.services.vllm_client import VLLMClient
from app.services.model_registry import ModelRegistry

EXCEL_PLANNER_SYSTEM_PROMPT = """
You are a senior full-stack engineer and expert Excel analyst. 
Your goal is to parse user natural-language instructions and map them to specific workbook actions.

You must output a valid JSON object matching the ExcelActionPlan schema.

Available action_type values:
- create_formula_column: Add a new column with a formula.
- overwrite_formula_column: Replace values in an existing column with a formula.
- create_helper_column: Create a hidden or secondary column for intermediate logic.
- create_summary_sheet: Create a new sheet for aggregations.
- create_dashboard_sheet: Create a high-level KPI dashboard sheet.
- perform_lookup: Use XLOOKUP or VLOOKUP to pull data from another sheet.
- classify_values: Use IF/IFS logic to bucketize values.
- clean_text_column: Use TRIM, SUBSTITUTE, LEFT, RIGHT, etc. to clean strings.
- date_transformation: Transform date formats or extract Year/Month.
- add_flag_column: Add a boolean or indicator column.
- ask_clarification: If the instruction is too ambiguous.

Rules:
1. Always prefer native Excel formulas.
2. If multiple sheets exist, ensure you identify the correct target sheet.
3. If headers are provided in the context, use them in the formula if appropriate, or use cell references (e.g., A2).
4. For formula_pattern, use A2, B2 style references which will be filled down.
5. If the user asks for a dashboard, propose a summary sheet with KPIs.
6. Use double quotes for strings inside formulas.

Context will be provided with sheet names and headers.
"""

class ExcelSessionManager:
    def __init__(self, max_sessions: int = 50):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self.max_sessions = max_sessions

    def create_session(self, filename: str, content: bytes) -> str:
        session_id = str(uuid.uuid4())
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
        self._sessions[session_id] = {
            "wb": wb,
            "filename": filename,
            "active_sheet": wb.active.title if wb.active else wb.sheetnames[0]
        }
        # TODO: Implement LRU eviction if needed
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, wb: Workbook):
        if session_id in self._sessions:
            self._sessions[session_id]["wb"] = wb

    def set_active_sheet(self, session_id: str, sheet_name: str):
        if session_id in self._sessions:
            self._sessions[session_id]["active_sheet"] = sheet_name

class ExcelService:
    def __init__(self, session_manager: ExcelSessionManager, vllm_client: VLLMClient, model_registry: ModelRegistry):
        self.session_manager = session_manager
        self.vllm_client = vllm_client
        self.model_registry = model_registry

    def get_preview(self, session_id: str, sheet_name: Optional[str] = None, max_rows: int = 50) -> Optional[ExcelSheetPreview]:
        session = self.session_manager.get_session(session_id)
        if not session:
            return None
        
        wb: Workbook = session["wb"]
        if not sheet_name:
            sheet_name = session["active_sheet"]
        
        if sheet_name not in wb.sheetnames:
            return None
        
        ws: Worksheet = wb[sheet_name]
        
        headers = []
        rows = []
        
        # Detect headers and rows
        for i, row in enumerate(ws.iter_rows(max_row=max_rows, values_only=True)):
            if i == 0:
                headers = [str(cell) if cell is not None else f"Column {j+1}" for j, cell in enumerate(row)]
            else:
                rows.append(list(row))
        
        return ExcelSheetPreview(
            name=sheet_name,
            headers=headers,
            rows=rows,
            total_rows=ws.max_row,
            total_columns=ws.max_column
        )

    def get_metadata(self, session_id: str) -> Optional[ExcelSessionMetadata]:
        session = self.session_manager.get_session(session_id)
        if not session:
            return None
        
        wb: Workbook = session["wb"]
        return ExcelSessionMetadata(
            session_id=session_id,
            filename=session["filename"],
            sheets=wb.sheetnames,
            active_sheet=session["active_sheet"],
            preview=self.get_preview(session_id)
        )

    async def plan_action(self, session_id: str, user_instruction: str, model_id: Optional[str] = None) -> ExcelActionPlan:
        metadata = self.get_metadata(session_id)
        if not metadata:
            raise ValueError("Session not found")
        
        preview = metadata.preview
        context = {
            "filename": metadata.filename,
            "sheets": metadata.sheets,
            "active_sheet": metadata.active_sheet,
            "headers": preview.headers if preview else []
        }

        messages = [
            {"role": "system", "content": EXCEL_PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context: {json.dumps(context)}\nInstruction: {user_instruction}"}
        ]

        requested_model_id = model_id or self.model_registry.default_model_id
        chain = self.model_registry.build_fallback_chain(requested_model_id)
        last_error: Exception | None = None

        for candidate_model_id in chain:
            profile = self.model_registry.get(candidate_model_id)
            try:
                response = await self.vllm_client.chat(
                    model_ref=profile.runtime.model_ref,
                    messages=messages,
                    temperature=0.0,  # Strict JSON
                    max_tokens=800,
                )

                text = response["choices"][0]["message"]["content"]
                start = text.find("{")
                end = text.rfind("}") + 1
                if start != -1 and end != -1:
                    plan_data = json.loads(text[start:end])
                else:
                    plan_data = json.loads(text)
                return ExcelActionPlan(**plan_data)
            except (InferenceError, TimeoutError, json.JSONDecodeError, KeyError, ValueError) as exc:
                last_error = exc
                continue

        if last_error:
            raise ValueError(f"No available model could plan Excel action: {last_error}") from last_error
        raise ValueError("No available model could plan Excel action")

    def apply_action(self, session_id: str, plan: ExcelActionPlan) -> str:
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        
        wb: Workbook = session["wb"]
        sheet_name = plan.sheet_name or session["active_sheet"]
        
        if plan.action_type == "ask_clarification":
            return plan.clarification_question or "I'm not sure what you want to do. Could you clarify?"

        if sheet_name not in wb.sheetnames:
            if plan.action_type in ("create_summary_sheet", "create_dashboard_sheet"):
                ws = wb.create_sheet(sheet_name)
            else:
                raise ValueError(f"Sheet '{sheet_name}' not found")
        else:
            ws = wb[sheet_name]

        summary = f"Applied {plan.action_type}"

        if plan.action_type in ("create_formula_column", "overwrite_formula_column", "create_helper_column", "add_flag_column", "classify_values", "clean_text_column", "date_transformation"):
            target_col_idx = -1
            if plan.action_type == "overwrite_formula_column" and plan.target_column_name:
                for idx, cell in enumerate(ws[1], 1):
                    if cell.value == plan.target_column_name:
                        target_col_idx = idx
                        break
            
            if target_col_idx == -1:
                # Add new column at the end
                target_col_idx = ws.max_column + 1
                ws.cell(row=1, column=target_col_idx, value=plan.target_column_name or "New Column")
            
            # Write formula
            if plan.formula_pattern:
                # Naive fill down: we assume the pattern uses A2 style refs and we just increment row
                # Better: use openpyxl's internal formula relative handling if possible, 
                # but simple string replacement for '2' -> row_idx is often enough for a start.
                # Actually, openpyxl handles string formulas fine.
                for row_idx in range(2, ws.max_row + 1):
                    # For now, we assume the model gave us a formula for row 2
                    # To truly fill down, we might need to adjust relative refs.
                    # Simple heuristic: if formula contains '2', replace with row_idx
                    # But wait, openpyxl doesn't auto-adjust.
                    # Let's just write the same string if the model is smart enough to use relative refs 
                    # OR we do the adjustment.
                    formula = plan.formula_pattern
                    # Very simple adjustment: replace '2' (surrounded by non-digits) with row_idx
                    # This is risky, but works for simple cases.
                    adjusted_formula = re.sub(r'(?<=[A-Z])2(?!\d)', str(row_idx), formula)
                    ws.cell(row=row_idx, column=target_col_idx, value=adjusted_formula)
            
            summary = f"Added column '{plan.target_column_name or 'New Column'}' with formula '{plan.formula_pattern}' to sheet '{sheet_name}'"

        elif plan.action_type == "perform_lookup":
             # Similar to above, but specifically for lookups
             pass # Implementation pending more robust logic

        self.session_manager.update_session(session_id, wb)
        return summary

    def save_workbook(self, session_id: str) -> bytes:
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        
        wb: Workbook = session["wb"]
        out = io.BytesIO()
        wb.save(out)
        return out.getvalue()
