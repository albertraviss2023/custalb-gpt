from __future__ import annotations

from typing import Any, Literal
from pydantic import Field
from .schemas import ApiModel

ExcelActionType = Literal[
    "create_formula_column",
    "overwrite_formula_column",
    "create_helper_column",
    "create_summary_sheet",
    "create_dashboard_sheet",
    "perform_lookup",
    "classify_values",
    "clean_text_column",
    "date_transformation",
    "add_flag_column",
    "ask_clarification"
]

class ExcelActionPlan(ApiModel):
    action_type: ExcelActionType
    sheet_name: str | None = None
    target_column_name: str | None = None
    formula_pattern: str | None = None
    source_columns: list[str] = Field(default_factory=list)
    fill_down: bool = True
    insert_position: Literal["end", "next_to_source"] = "end"
    explanation: str | None = None
    clarification_question: str | None = None

class ExcelSheetPreview(ApiModel):
    name: str
    headers: list[str]
    rows: list[list[Any]]
    total_rows: int
    total_columns: int

class ExcelSessionMetadata(ApiModel):
    session_id: str
    filename: str
    sheets: list[str]
    active_sheet: str
    preview: ExcelSheetPreview | None = None

class ExcelActionResponse(ApiModel):
    session_id: str
    summary: str
    changed_sheet: str
    preview: ExcelSheetPreview
    action_plan: ExcelActionPlan


class ExcelSetActiveSheetRequest(ApiModel):
    sheet_name: str
