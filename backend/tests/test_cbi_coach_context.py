from __future__ import annotations

from app.models.schemas import ChatCompletionRequest, MessageInput
from app.services.chat_service import ChatService


def test_cbi_context_includes_scorecard_schema_and_weights() -> None:
    request = ChatCompletionRequest(
        model="qwen_fast_vllm",
        stream=False,
        addon_id="competency_interview_coach",
        interview_role="Monitoring and Evaluation Manager",
        interview_panel_members=5,
        messages=[MessageInput(role="user", content="Start CBI practice")],
    )

    prompt = ChatService._build_interview_context(request, "Start CBI practice")
    assert prompt is not None
    assert "CBI_SCORECARD_JSON" in prompt
    assert "Results Measurement (Weight: 24%)" in prompt
    assert "Analytical Rigor (Weight: 20%)" in prompt
    assert "Dr. Elena Sokolov" in prompt
    assert "Mandatory Opening Flow" in prompt
    assert "PANEL_SPEAKER:" in prompt
    assert "Primary questions MUST name the competency" in prompt
    assert "Mandatory probing for each response" in prompt


def test_non_cbi_addon_has_no_interview_context() -> None:
    request = ChatCompletionRequest(
        model="qwen_fast_vllm",
        stream=False,
        addon_id="excel_data_analyst",
        messages=[MessageInput(role="user", content="hello")],
    )
    assert ChatService._build_interview_context(request, "hello") is None
