from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException, status

from app.db.repository import Repository
from app.models.schemas import ChatCompletionRequest, MessageInput
from app.services.addon_store import AddonStore
from app.services.model_registry import ModelRegistry
from app.services.vllm_client import InferenceError, VLLMClient


OOM_MARKERS = ("out of memory", "cuda", "insufficient", "alloc", "oom")
STATIC_CONTEXT_CEILING = 4096
CBI_CONTEXT_CEILING = 2048
CBI_MAX_OUTPUT_TOKENS = 320
TOKEN_ESTIMATE_SAFETY_MARGIN = 64
RECENT_RESUME_MESSAGES = 12
COMPACTION_TRIGGER_RATIO = 0.98
COMPACTION_KEEP_RECENT_MESSAGES = 8
THINKING_TEMPERATURES = {
    "fast": 0.15,
    "balanced": 0.35,
    "deep": 0.55,
}
RESPONSE_LENGTH_TOKENS = {
    "concise": 256,
    "standard": 1024,
    "detailed": 2048,
}
THINKING_TOKEN_MULTIPLIER = {
    "fast": 0.75,
    "balanced": 1.0,
    "deep": 1.5,
}
COMMON_TYPOS = {
    "teh": "the",
    "adn": "and",
    "recieve": "receive",
    "seperate": "separate",
    "anlysis": "analysis",
    "analysys": "analysis",
}
CBI_CONTROL_MARKERS = (
    "start cbi practice now",
    "ask exactly one primary",
    "end this interview now",
    "generate final cbi performance report now",
    "interview timer has reached",
    "conclude the panel",
)

CBI_ROLE_PROFILES: dict[str, dict[str, Any]] = {
    "program manager": {
        "track_name": "Program Management",
        "competencies": [
            {
                "name": "Strategic Delivery",
                "weight": 24,
                "signals": ["roadmap execution", "cross-team milestone control", "measurable outcomes"],
            },
            {
                "name": "Stakeholder Management",
                "weight": 22,
                "signals": ["executive alignment", "conflict navigation", "expectation setting"],
            },
            {
                "name": "Problem Solving",
                "weight": 18,
                "signals": ["root-cause analysis", "trade-off decisions", "risk mitigation"],
            },
            {
                "name": "Communication",
                "weight": 16,
                "signals": ["clarity", "structured messaging", "decision framing"],
            },
            {
                "name": "Leadership and Influence",
                "weight": 20,
                "signals": ["leading without authority", "ownership", "driving decisions"],
            },
        ],
    },
    "monitoring and evaluation manager": {
        "track_name": "Monitoring and Evaluation",
        "competencies": [
            {
                "name": "Results Measurement",
                "weight": 24,
                "signals": ["indicator design", "baseline-target logic", "results interpretation"],
            },
            {
                "name": "Analytical Rigor",
                "weight": 20,
                "signals": ["method selection", "validity checks", "bias control"],
            },
            {
                "name": "Adaptive Management",
                "weight": 18,
                "signals": ["course correction", "learning loops", "decision support"],
            },
            {
                "name": "Stakeholder Communication",
                "weight": 18,
                "signals": ["clear evidence narratives", "executive reporting", "action-oriented insights"],
            },
            {
                "name": "Governance and Quality",
                "weight": 20,
                "signals": ["data quality assurance", "ethics/compliance", "auditability"],
            },
        ],
    },
}


@dataclass(slots=True)
class CompletionResult:
    text: str
    used_model_id: str
    fallback_reason: str | None
    usage: dict[str, int | None]
    attempted_models: list[str]
    telemetry: dict[str, Any]


class ChatService:
    def __init__(
        self,
        *,
        repository: Repository,
        model_registry: ModelRegistry,
        inference_client: VLLMClient,
        addon_store: AddonStore | None = None,
    ) -> None:
        self.repository = repository
        self.model_registry = model_registry
        self.inference_client = inference_client
        self.addon_store = addon_store

    def _resolve_model_id(self, request: ChatCompletionRequest) -> str:
        if request.model:
            if not self.model_registry.exists(request.model):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown model id")
            return request.model

        if request.chat_id:
            chat = self.repository.get_chat(request.chat_id)
            if not chat:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
            if chat.selected_model_id and self.model_registry.exists(chat.selected_model_id):
                return chat.selected_model_id

        stored_default = self.repository.get_default_model_id(self.model_registry.default_model_id)
        if self.model_registry.exists(stored_default):
            return stored_default
        return self.model_registry.default_model_id

    @staticmethod
    def _latest_user_query(messages: list[MessageInput]) -> str | None:
        for message in reversed(messages):
            if message.role != "user":
                continue
            if isinstance(message.content, str):
                text = message.content.strip()
                if text:
                    return text
            elif isinstance(message.content, list):
                parts = [part.text or "" for part in message.content if part.type == "text"]
                joined = " ".join(parts).strip()
                if joined:
                    return joined
        return None

    async def _build_web_context(self, query: str | None) -> str | None:
        if not query:
            return None
        compact_query = " ".join(query.split())[:200]
        if not compact_query:
            return None

        lines: list[str] = ["Web mode context (bounded excerpts, verify critical facts):"]
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": compact_query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1,
                    },
                )
                payload = response.json()
        except Exception:
            return None

        abstract_text = str(payload.get("AbstractText") or "").strip()
        abstract_url = str(payload.get("AbstractURL") or "").strip()
        if abstract_text:
            lines.append(f"- Summary: {abstract_text[:420]}")
            if abstract_url:
                lines.append(f"  Source: {abstract_url}")

        related = payload.get("RelatedTopics")
        appended = 0
        if isinstance(related, list):
            for topic in related:
                if appended >= 3:
                    break
                text = ""
                url = ""
                if isinstance(topic, dict):
                    text = str(topic.get("Text") or "").strip()
                    url = str(topic.get("FirstURL") or "").strip()
                    if not text and isinstance(topic.get("Topics"), list):
                        for nested in topic["Topics"]:
                            if isinstance(nested, dict):
                                text = str(nested.get("Text") or "").strip()
                                url = str(nested.get("FirstURL") or "").strip()
                                if text:
                                    break
                if not text:
                    continue
                lines.append(f"- {text[:240]}")
                if url:
                    lines.append(f"  Source: {url}")
                appended += 1

        if len(lines) == 1:
            return None
        merged = "\n".join(lines).strip()
        return merged[:1800]

    @staticmethod
    def _normalize_interview_role(role: str) -> str:
        return " ".join(role.lower().split())

    @classmethod
    def _resolve_cbi_profile(cls, role: str) -> dict[str, Any]:
        normalized = cls._normalize_interview_role(role)
        if normalized in CBI_ROLE_PROFILES:
            return CBI_ROLE_PROFILES[normalized]
        if "monitor" in normalized and "evaluat" in normalized:
            return CBI_ROLE_PROFILES["monitoring and evaluation manager"]
        return CBI_ROLE_PROFILES["program manager"]

    @classmethod
    def _build_interview_context(
        cls,
        request: ChatCompletionRequest,
        latest_query: str | None = None,
    ) -> str | None:
        if request.addon_id != "competency_interview_coach":
            return None
        role = (request.interview_role or "").strip() or "the target role"
        level = request.interview_role_level or "P3"
        panel_members = request.interview_panel_members or 3
        panel_members = max(1, min(panel_members, 5))
        
        # Realistic UN-style diverse panel
        full_panel_roster = [
            ("Dr. Elena Sokolov", "Panel Chair", "Switzerland", "female", "en-gb", "formal", "structured"),
            ("Kwame Mensah", "Technical Lead", "Ghana", "male", "auto", "probing", "strict"),
            ("Maria Garcia", "HR Representative", "Spain", "female", "auto", "supportive", "conversational"),
            ("Chen Wei", "Director of Operations", "China", "male", "auto", "skeptical", "strict"),
            ("Linda Miller", "Stakeholder Representative", "USA", "female", "en-us", "neutral", "structured"),
        ]
        
        if request.interview_panelists:
            custom_roster = []
            for idx, panelist in enumerate(request.interview_panelists[:panel_members]):
                custom_roster.append((
                    panelist.name.strip() or f"Panelist {idx + 1}",
                    panelist.title.strip() or "Panel Member",
                    (panelist.nationality or "").strip() or "Not specified",
                    (panelist.gender or "").strip().lower() or "unknown",
                    (panelist.accent or "").strip().lower() or "auto",
                    (panelist.tone or "").strip().lower() or "neutral",
                    (panelist.speaking_style or "").strip().lower() or "structured"
                ))
            if len(custom_roster) < panel_members:
                existing_names = {p[0] for p in custom_roster}
                for default_p in full_panel_roster:
                    if len(custom_roster) >= panel_members:
                        break
                    if default_p[0] not in existing_names:
                        custom_roster.append(default_p)
            panel_roster = custom_roster[:panel_members]
        else:
            panel_roster = full_panel_roster[:panel_members]
            
        panel_lines = [
            f"- {name} ({title}, {nat}, gender={gen}, accent={acc}, tone={tone}, style={style})"
            for name, title, nat, gen, acc, tone, style in panel_roster
        ]
        chair_name = panel_roster[0][0]
        
        intensity = request.interview_realism_intensity or "medium"
        intensity_map = {
            "low": "Supportive and encouraging. Minimal probing.",
            "medium": "Standard UN CBI. Balanced probing. Professional and neutral tone.",
            "high": "Strict and rigorous. Deep probing. Challenges vague responses.",
            "extreme": "Highly critical. Layered follow-ups (5-6 levels deep). Challenges assumptions."
        }
        intensity_desc = intensity_map.get(intensity, intensity_map["medium"])
        
        org_type = request.interview_organization_type or "un"
        org_name = (request.interview_organization_name or "").strip() or ("United Nations" if org_type == "un" else "International Organization")
        org_location = (request.interview_location or "").strip() or "Geneva, Switzerland"
        hq_status = "HQ" if request.interview_is_hq else "Regional/Field Office"
        interview_duration = request.interview_duration_minutes or 30
        
        profile = cls._resolve_cbi_profile(role)
        
        # Adjust competencies based on level
        competencies = profile["competencies"]
        if level in ("P4", "P5", "D1", "D2"):
            # Add managerial competencies if not present
            managerial = [
                {"name": "Leadership", "weight": 15, "signals": ["Motivating", "Empowering", "Role model"]},
                {"name": "Vision", "weight": 15, "signals": ["Strategic perspective", "Inspirational"]},
                {"name": "Managing Performance", "weight": 15, "signals": ["Fairness", "Coaching", "Monitoring"]},
                {"name": "Strategic Thinking", "weight": 15, "signals": ["Analytical", "Complex scenarios"]}
            ]
            # Ensure at least 2 managerial competencies are included
            existing_names = {c["name"] for c in competencies}
            added = 0
            for m in managerial:
                if added >= 2: break
                if m["name"] not in existing_names:
                    competencies.append(m)
                    added += 1

        competency_lines = []
        for item in competencies:
            signals = ", ".join(item["signals"])
            competency_lines.append(f"- {item['name']} (Weight: {item['weight']}%): Indicators include {signals}")

        is_opening = latest_query and any(token in latest_query.lower() for token in ("start", "begin", "kick off", "ready"))
        
        introduction_flow = (
            f"Mandatory Opening Flow:\n"
            f"1. {chair_name} (Chair) welcomes candidate to {org_name} ({hq_status}) in {org_location} for role level {level}.\n"
            f"2. Chair introduces each panelist individually with name, role, and location.\n"
            f"3. Chair explains the UN CBI format: focus on past behavior, STAR structure, and depth probing.\n"
            f"4. Chair lists competencies to be assessed.\n"
            f"5. Chair confirms candidate readiness and asks the first competency question."
        ) if is_opening else "Continue the interview flow naturally, adhering to established panel personalities."

        # Delivery signals integration
        delivery_signals = request.delivery_signals or {}
        delivery_context = (
            "CANDIDATE DELIVERY SIGNALS (Last turn):\n"
            + "\n".join([f"- {k}: {v}" for k, v in delivery_signals.items()])
            + "\nAdjust panel behavior based on these signals (e.g., if hesitant, Chair might offer encouragement or technical lead might probe harder)."
        ) if delivery_signals else ""

        return (
            "SYSTEM ROLE: High-Fidelity UN Interview Panel Simulation Engine.\n"
            "CORE MISSION: Strictly follow real UN CBI standards for role level " + level + ".\n\n"
            "CONTEXT:\n"
            f"- Role: {role} (Level: {level})\n"
            f"- Organization: {org_name} ({hq_status})\n"
            f"- Location: {org_location}\n"
            f"- Realism Intensity: {intensity.upper()} - {intensity_desc}\n"
            f"- Duration: {interview_duration} minutes\n\n"
            "PANEL COMPOSITION:\n"
            + "\n".join(panel_lines) + "\n\n"
            "BEHAVIOR RULES:\n"
            "- Consistency: Panelists must stick to assigned tone, accent, and style.\n"
            "- CBI Questioning: Primary questions MUST name the competency (e.g. 'This assesses Teamwork...').\n"
            "- Probing Strategy: Mandatory probing for each response. Depth depends on intensity and role level.\n"
            "- Realistic Transitions: Signal competency shifts clearly.\n"
            "- Anti-Hallucination: Use MCP (mcp_fetch_org_info, mcp_fetch_competency_framework) for institutional details.\n"
            f"- {introduction_flow}\n\n"
            f"{delivery_context}\n\n"
            "OUTPUT FORMAT (Strict):\n"
            "PANEL_SPEAKER: <Name> | <Role> | <Nationality> | <Gender> | <Accent>\n"
            "PANEL_TEXT: <Content>\n\n"
            "EVALUATION ENGINE (CBI_SCORECARD_JSON):\n"
            "- Standard: Evidence-based UN rubric (1-5 scale).\n"
            "- Evaluates BOTH Content (STAR) and Delivery (Confidence, Clarity, Presence).\n"
            "- Output JSON then Markdown report.\n"
            '- JSON Schema: {"role":"string","level":"string","overall_readiness_0_to_100":number,"competencies":[{"name":"string","score_1_to_5":number,"evidence":"string","gaps":"string"}],"delivery":{"confidence":number,"clarity":number,"presence":number,"feedback":"string"},"panel_summary":"string","verdict":"string"}\n\n'
            "COMPETENCIES TO ASSESS:\n"
            + "\n".join(competency_lines)
        )

    @staticmethod
    def _estimate_text_tokens(text: str) -> int:
        stripped = text.strip()
        if not stripped:
            return 0
        # Fast heuristic suitable for runtime guardrails.
        return max(1, (len(stripped) + 3) // 4)

    @classmethod
    def _estimate_message_tokens(cls, message: dict[str, Any]) -> int:
        content = message.get("content")
        base = 4  # per-message protocol overhead
        if isinstance(content, str):
            return base + cls._estimate_text_tokens(content)
        if isinstance(content, list):
            total = base
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += cls._estimate_text_tokens(str(part.get("text", "")))
                elif isinstance(part, dict) and part.get("type") == "image_url":
                    total += 64
            return total
        return base

    @classmethod
    def _estimate_messages_tokens(cls, messages: list[dict[str, Any]]) -> int:
        return sum(cls._estimate_message_tokens(message) for message in messages) + 2

    @staticmethod
    def _pressure_status(active_tokens: int, ceiling: int) -> str:
        if ceiling <= 0:
            return "unknown"
        ratio = active_tokens / ceiling
        if ratio < 0.75:
            return "green"
        if ratio < 0.9:
            return "yellow"
        return "red"

    @classmethod
    def _enforce_context_budget(
        cls,
        runtime_messages: list[dict[str, Any]],
        *,
        context_ceiling: int,
        max_tokens: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        budget = max(256, min(context_ceiling, STATIC_CONTEXT_CEILING))
        output_reserve = max(128, min(max_tokens, budget // 3))
        input_budget = max(128, budget - output_reserve - TOKEN_ESTIMATE_SAFETY_MARGIN)

        if not runtime_messages:
            telemetry = {
                "context_ceiling_tokens": budget,
                "context_input_budget_tokens": input_budget,
                "active_input_tokens": 0,
                "pressure_status": "green",
                "trimmed_messages": 0,
            }
            return runtime_messages, telemetry

        anchor: dict[str, Any] | None = None
        tail_messages: list[dict[str, Any]] = runtime_messages
        if runtime_messages[0].get("role") in {"system"}:
            anchor = runtime_messages[0]
            tail_messages = runtime_messages[1:]

        if anchor and isinstance(anchor.get("content"), str):
            anchor_tokens = cls._estimate_message_tokens(anchor)
            if anchor_tokens > input_budget:
                # Hard-truncate oversized system payloads so tiny runtime windows (e.g. 1k) still accept the request.
                max_chars = max(256, (input_budget - 16) * 4)
                anchor = {**anchor, "content": str(anchor["content"])[:max_chars]}

        kept_reversed: deque[dict[str, Any]] = deque()
        consumed = cls._estimate_message_tokens(anchor) if anchor else 0
        trimmed = 0

        for message in reversed(tail_messages):
            token_cost = cls._estimate_message_tokens(message)
            if consumed + token_cost <= input_budget:
                kept_reversed.appendleft(message)
                consumed += token_cost
            else:
                trimmed += 1

        bounded: list[dict[str, Any]] = []
        if anchor:
            bounded.append(anchor)
        bounded.extend(list(kept_reversed))

        active_tokens = cls._estimate_messages_tokens(bounded)
        telemetry = {
            "context_ceiling_tokens": budget,
            "context_input_budget_tokens": input_budget,
            "active_input_tokens": active_tokens,
            "pressure_status": cls._pressure_status(active_tokens, budget),
            "trimmed_messages": trimmed,
        }
        return bounded, telemetry

    @staticmethod
    def _supports_system_role(model_ref: str) -> bool:
        # TitanML Gemma2 chat template currently rejects system role on vLLM.
        return model_ref != "gemma-fast-vllm"

    def _build_request_messages(self, request: ChatCompletionRequest) -> tuple[list[MessageInput], str | None]:
        if not request.chat_id:
            return request.messages, None

        chat = self.repository.get_chat(request.chat_id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        persisted_tail = chat.messages[-RECENT_RESUME_MESSAGES:]
        merged: list[MessageInput] = [
            MessageInput(role=message.role, content=message.content)
            for message in persisted_tail
            if message.role in {"user", "assistant"}
        ]

        incoming = request.messages
        if merged and incoming:
            first = incoming[0]
            tail = merged[-1]
            if tail.role == first.role and tail.content == first.content:
                incoming = incoming[1:]
        merged.extend(incoming)

        memory = self.repository.get_chat_memory(request.chat_id)
        summary = None
        if memory:
            summary_text = str(memory.get("summary_text", "")).strip()
            if summary_text:
                summary = summary_text
        return merged, summary

    def _distill_compaction_summary(self, existing_summary: str, stale_messages: list[MessageInput]) -> str:
        snippets: list[str] = []
        for message in stale_messages[-24:]:
            if not isinstance(message.content, str):
                continue
            text = " ".join(message.content.split())
            if not text:
                continue
            if len(text) > 180:
                text = text[:180].rstrip(" ,.;:-") + "..."
            actor = "User" if message.role == "user" else "Assistant"
            snippets.append(f"- {actor}: {text}")

        new_block = "Compacted history notes:\n" + "\n".join(snippets) if snippets else ""
        if existing_summary and new_block:
            merged = f"{existing_summary}\n\n{new_block}"
        else:
            merged = existing_summary or new_block
        merged = merged.strip()
        if len(merged) > 6000:
            merged = merged[-6000:]
        return merged

    def _maybe_compact_chat_context(self, *, chat_id: str, requested_model_id: str) -> dict[str, Any] | None:
        chat = self.repository.get_chat(chat_id)
        if not chat or not chat.messages:
            return None

        profile = self.model_registry.get(requested_model_id)
        context_ceiling = max(256, min(profile.limits.max_context_tokens, STATIC_CONTEXT_CEILING))
        trigger_tokens = int(context_ceiling * COMPACTION_TRIGGER_RATIO)

        memory = self.repository.get_chat_memory(chat_id)
        summary_text = str(memory.get("summary_text", "")) if memory else ""
        summary_tokens = self._estimate_text_tokens(summary_text)
        message_inputs = [
            MessageInput(role=message.role, content=message.content)
            for message in chat.messages
            if message.role in {"user", "assistant"}
        ]
        active_tokens = self._estimate_messages_tokens([
            {"role": message.role, "content": message.content}
            for message in message_inputs
        ]) + summary_tokens

        if active_tokens < trigger_tokens or len(message_inputs) <= COMPACTION_KEEP_RECENT_MESSAGES:
            return None

        stale_records = message_inputs[:-COMPACTION_KEEP_RECENT_MESSAGES]
        stale_db_ids = [message.id for message in chat.messages[:-COMPACTION_KEEP_RECENT_MESSAGES]]
        if not stale_records or not stale_db_ids:
            return None

        next_summary = self._distill_compaction_summary(summary_text, stale_records)
        next_summary_version = int(memory.get("summary_version", 0)) + 1 if memory else 1
        next_compaction_count = int(memory.get("compaction_count", 0)) + 1 if memory else 1
        last_compacted_message_id = stale_db_ids[-1]

        recent_for_estimate = message_inputs[-COMPACTION_KEEP_RECENT_MESSAGES:]
        post_tokens = self._estimate_messages_tokens([
            {"role": message.role, "content": message.content}
            for message in recent_for_estimate
        ]) + self._estimate_text_tokens(next_summary)

        self.repository.compact_chat_context(
            chat_id=chat_id,
            delete_message_ids=stale_db_ids,
            summary_text=next_summary,
            summary_version=next_summary_version,
            compaction_count=next_compaction_count,
            last_compacted_message_id=last_compacted_message_id,
            token_estimate=post_tokens,
        )
        self.repository.add_log_event(
            level="info",
            source="context_compactor",
            message="Compaction applied to chat context",
            chat_id=chat_id,
            context={
                "trigger_tokens": trigger_tokens,
                "active_tokens_before": active_tokens,
                "active_tokens_after": post_tokens,
                "pruned_messages": len(stale_db_ids),
                "summary_version": next_summary_version,
            },
        )
        return {
            "compaction_applied": True,
            "compaction_pruned_messages": len(stale_db_ids),
            "compaction_summary_version": next_summary_version,
            "active_tokens_before_compaction": active_tokens,
            "active_tokens_after_compaction": post_tokens,
        }

    def manual_compact_chat_context(self, *, chat_id: str, forget_message_ids: list[str]) -> dict[str, int]:
        chat = self.repository.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        selectable = [m for m in chat.messages if m.role in {"user", "assistant"}]
        if not selectable:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No compactable messages in chat")

        forget_set = {mid.strip() for mid in forget_message_ids if mid and mid.strip()}
        if not forget_set:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No messages selected to forget")

        stale_db_ids: list[str] = []
        stale_inputs: list[MessageInput] = []
        retained_inputs: list[MessageInput] = []
        for message in selectable:
            as_input = MessageInput(role=message.role, content=message.content)
            if message.id in forget_set:
                stale_db_ids.append(message.id)
                stale_inputs.append(as_input)
            else:
                retained_inputs.append(as_input)

        if not stale_db_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected messages were not found in chat")

        memory = self.repository.get_chat_memory(chat_id) or {}
        current_summary = str(memory.get("summary_text", ""))
        next_summary = self._distill_compaction_summary(current_summary, stale_inputs)
        next_summary_version = int(memory.get("summary_version", 0)) + 1
        next_compaction_count = int(memory.get("compaction_count", 0)) + 1
        last_compacted_message_id = stale_db_ids[-1]
        token_estimate = self._estimate_messages_tokens([
            {"role": msg.role, "content": msg.content}
            for msg in retained_inputs
        ]) + self._estimate_text_tokens(next_summary)

        self.repository.compact_chat_context(
            chat_id=chat_id,
            delete_message_ids=stale_db_ids,
            summary_text=next_summary,
            summary_version=next_summary_version,
            compaction_count=next_compaction_count,
            last_compacted_message_id=last_compacted_message_id,
            token_estimate=token_estimate,
        )
        self.repository.add_log_event(
            level="info",
            source="context_compactor",
            message="Manual selective compaction applied",
            chat_id=chat_id,
            context={
                "mode": "manual_selective_forget",
                "forgotten_messages": len(stale_db_ids),
                "summary_version": next_summary_version,
            },
        )
        return {
            "forgotten_messages": len(stale_db_ids),
            "summary_version": next_summary_version,
            "compaction_count": next_compaction_count,
            "token_estimate": token_estimate,
        }

    @staticmethod
    def _build_system_style_instruction(response_length: str, thinking_level: str) -> str:
        length_hint = {
            "concise": "Keep answers brief: aim for 1-3 short sentences unless the user asks for depth.",
            "standard": "Keep answers focused and moderately detailed.",
            "detailed": "Provide fuller detail, stay structured and be thorough.",
        }[response_length]
        thinking_hint = {
            "fast": "Optimize for speed and directness.",
            "balanced": "Balance speed and quality.",
            "deep": "Spend more effort on difficult reasoning and step-by-step logic.",
        }[thinking_level]

        instruction = (
            "Response policy:\n"
            f"- {length_hint}\n"
            f"- {thinking_hint}\n"
            "- Use clean markdown for structure.\n"
            "- Prefer short paragraphs and bullet points.\n"
            "- Use code blocks where appropriate for clarity.\n"
            "- Avoid very long walls of text unless explicitly requested."
        )
        if response_length == "concise":
            instruction += "\n- For concise mode, avoid code blocks unless the user explicitly asks for code."
        return instruction

    @staticmethod
    def _effective_context_ceiling(request: ChatCompletionRequest, model_ceiling: int) -> int:
        if request.addon_id == "competency_interview_coach":
            return min(model_ceiling, CBI_CONTEXT_CEILING)
        return model_ceiling

    @classmethod
    def _as_runtime_messages(
        cls,
        messages: list[MessageInput],
        *,
        response_length: str,
        thinking_level: str,
        memory_prompt: str | None = None,
        addon_prompt: str | None = None,
        attachment_prompt: str | None = None,
        allow_system_messages: bool = True,
    ) -> list[dict[str, Any]]:
        system_text_parts = [cls._build_system_style_instruction(response_length, thinking_level)]
        if memory_prompt:
            system_text_parts.append(
                "Conversation summary memory from prior turns (authoritative facts/preferences/open tasks):\n"
                f"{memory_prompt}"
            )
        if addon_prompt:
            system_text_parts.append(addon_prompt)
        if attachment_prompt:
            system_text_parts.append(attachment_prompt)
        system_text = "\n\n".join(system_text_parts).strip()

        runtime_messages: list[dict[str, Any]] = []
        for msg in messages:
            if isinstance(msg.content, list):
                parts = []
                for p in msg.content:
                    if p.type == "text":
                        parts.append({"type": "text", "text": p.text})
                    elif p.type == "image_url":
                        parts.append({"type": "image_url", "image_url": p.image_url})
                runtime_messages.append({"role": msg.role, "content": parts})
            else:
                runtime_messages.append({"role": msg.role, "content": msg.content})

        if allow_system_messages:
            return [{"role": "system", "content": system_text}, *runtime_messages]

        # Some chat templates (e.g. Gemma2 community templates in vLLM) reject system role.
        # Convert policy/add-on context into a user instruction while preserving role alternation.
        if runtime_messages and runtime_messages[0].get("role") == "user":
            first_content = runtime_messages[0].get("content")
            if isinstance(first_content, str):
                runtime_messages[0]["content"] = f"Instructions:\n{system_text}\n\nUser request:\n{first_content}"
                return runtime_messages
        return [{"role": "user", "content": f"Instructions:\n{system_text}"}, *runtime_messages]

    def _build_attachment_prompt(self, attachment_ids: list[str]) -> str | None:
        if not attachment_ids:
            return None

        uploads = self.repository.list_uploads_by_ids(attachment_ids)
        if not uploads:
            return None

        allowed_extensions = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".py", ".sql", ".xml"}
        lines: list[str] = [
            "Attached files for this chat (use these as working context when relevant):",
        ]

        for upload in uploads[:8]:
            if upload.status != "completed":
                continue
            storage_path = self.repository.get_upload_storage_path(upload.id)
            if not storage_path:
                continue
            entry = (
                f"- {upload.original_name} (upload_id={upload.id}, size={upload.total_size_bytes} bytes, status={upload.status})"
            )
            lines.append(entry)

            suffix = Path(upload.original_name).suffix.lower()
            if suffix not in allowed_extensions:
                continue
            if upload.total_size_bytes > 2 * 1024 * 1024:
                continue

            try:
                preview = Path(storage_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            preview = preview.strip()
            if not preview:
                continue
            preview = preview[:3000]
            lines.append(f"  preview:\n{preview}")

        if len(lines) <= 1:
            return None
        lines.append("If a file is binary or not previewed, acknowledge it and ask for the needed sheet/table details.")
        return "\n".join(lines)

    @staticmethod
    def _resolve_generation_controls(
        request: ChatCompletionRequest,
        max_output_tokens_cap: int,
    ) -> tuple[float, int]:
        temperature = request.temperature
        if temperature is None:
            temperature = THINKING_TEMPERATURES[request.thinking_level]

        if request.max_tokens is not None:
            max_tokens = min(request.max_tokens, max_output_tokens_cap)
        else:
            base_tokens = RESPONSE_LENGTH_TOKENS[request.response_length]
            multiplier = THINKING_TOKEN_MULTIPLIER[request.thinking_level]
            max_tokens = int(base_tokens * multiplier)
            max_tokens = max(32, min(max_tokens, max_output_tokens_cap))

        return temperature, max_tokens

    @staticmethod
    def _text_from_message_content(content: str | list[Any]) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    part_type = str(part.get("type", ""))
                    if part_type == "text":
                        parts.append(str(part.get("text", "")))
                else:
                    part_type = getattr(part, "type", "")
                    if part_type == "text":
                        parts.append(str(getattr(part, "text", "")))
            return " ".join(parts).strip()
        return ""

    @staticmethod
    def _extract_cbi_scorecard_segment(text: str) -> tuple[int, int] | None:
        marker = "CBI_SCORECARD_JSON:"
        marker_idx = text.find(marker)
        if marker_idx < 0:
            return None
        start = text.find("{", marker_idx)
        if start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return (start, idx + 1)
        return None

    @classmethod
    def _candidate_evidence_stats(cls, messages: list[MessageInput]) -> dict[str, int]:
        evidence_turns = 0
        evidence_words = 0
        star_hits = 0
        star_terms = (
            "situation",
            "task",
            "action",
            "result",
            "impact",
            "outcome",
            "metric",
            "measurable",
            "stakeholder",
            "challenge",
        )
        for message in messages:
            if message.role != "user":
                continue
            raw = cls._text_from_message_content(message.content)
            if not raw:
                continue
            lowered = raw.lower()
            if any(marker in lowered for marker in CBI_CONTROL_MARKERS):
                continue
            words = [token for token in raw.split() if token.strip()]
            if len(words) < 4:
                continue
            evidence_turns += 1
            evidence_words += len(words)
            star_hits += sum(1 for term in star_terms if term in lowered)
        return {
            "turns": evidence_turns,
            "words": evidence_words,
            "star_hits": star_hits,
        }

    @classmethod
    def _calibrate_cbi_scorecard(
        cls,
        text: str,
        request: ChatCompletionRequest,
        request_messages: list[MessageInput],
    ) -> str:
        if request.addon_id != "competency_interview_coach":
            return text
        segment = cls._extract_cbi_scorecard_segment(text)
        if not segment:
            return text
        start, end = segment
        try:
            parsed = json.loads(text[start:end])
        except json.JSONDecodeError:
            return text
        if not isinstance(parsed, dict):
            return text

        stats = cls._candidate_evidence_stats(request_messages)
        turns = stats["turns"]
        words = stats["words"]
        star_hits = stats["star_hits"]
        current_readiness = int(parsed.get("overall_readiness_0_to_100") or 0)

        if turns == 0 or words == 0:
            target_readiness = 12
        else:
            target_readiness = int(min(92, 24 + (turns * 7) + (min(words, 260) * 0.18) + (star_hits * 3)))
            if words < 20:
                target_readiness = min(target_readiness, 35)
            elif words < 40:
                target_readiness = min(target_readiness, 48)
            if star_hits == 0:
                target_readiness = min(target_readiness, 60)

        if current_readiness <= target_readiness and turns > 0:
            return text

        parsed["overall_readiness_0_to_100"] = max(0, min(100, target_readiness))
        competencies = parsed.get("competencies")
        if isinstance(competencies, list):
            adjusted: list[dict[str, Any]] = []
            for item in competencies:
                if not isinstance(item, dict):
                    continue
                score = int(item.get("score_1_to_5") or 1)
                if turns == 0:
                    score = 1
                    item["evidence"] = "No substantive interview evidence was provided by the candidate."
                    item["gaps"] = "Panel could not evaluate this competency due to missing behavioral examples."
                    item["improvement"] = "Use STAR: provide one concrete past example with actions and measurable results."
                else:
                    scaled = round(score * (target_readiness / max(current_readiness, 1)))
                    score = max(1, min(score, scaled if scaled > 0 else 1))
                item["score_1_to_5"] = int(max(1, min(5, score)))
                adjusted.append(item)
            parsed["competencies"] = adjusted

        if turns == 0:
            parsed["panel_summary"] = (
                "Insufficient evidence to assess performance. Candidate responses did not include usable behavioral examples."
            )
            parsed["next_best_question"] = (
                "Please answer one competency question using STAR with concrete actions, decisions, and measurable outcomes."
            )

        rebuilt_json = json.dumps(parsed, ensure_ascii=True, separators=(",", ":"))
        return f"{text[:start]}{rebuilt_json}{text[end:]}"

    @staticmethod
    def _is_cbi_report_request(messages: list[MessageInput]) -> bool:
        for message in reversed(messages):
            if message.role != "user":
                continue
            if isinstance(message.content, str):
                lowered = message.content.lower()
            else:
                lowered = " ".join(
                    str(part.text or "").lower()
                    for part in message.content
                    if getattr(part, "type", "") == "text"
                )
            if not lowered.strip():
                continue
            return (
                "final cbi performance report" in lowered
                or "end this interview now" in lowered
                or "conclude the panel" in lowered
            )
        return False

    @classmethod
    def _build_generated_cbi_scorecard(
        cls,
        request: ChatCompletionRequest,
        request_messages: list[MessageInput],
    ) -> dict[str, Any]:
        role = (request.interview_role or "Target Role").strip()
        profile = cls._resolve_cbi_profile(role)
        stats = cls._candidate_evidence_stats(request_messages)
        turns = stats["turns"]
        words = stats["words"]
        star_hits = stats["star_hits"]
        readiness = 12 if turns == 0 else int(min(90, 24 + (turns * 7) + (min(words, 260) * 0.18) + (star_hits * 3)))
        if turns > 0 and words < 20:
            readiness = min(readiness, 35)
        elif turns > 0 and words < 40:
            readiness = min(readiness, 48)
        if turns > 0 and star_hits == 0:
            readiness = min(readiness, 60)

        if readiness <= 20:
            base_score = 1
        elif readiness <= 40:
            base_score = 2
        elif readiness <= 65:
            base_score = 3
        elif readiness <= 82:
            base_score = 4
        else:
            base_score = 5

        competencies: list[dict[str, Any]] = []
        for item in profile["competencies"]:
            competencies.append({
                "name": item["name"],
                "weight": int(item["weight"]),
                "score_1_to_5": int(base_score),
                "evidence": (
                    "No substantive interview evidence was provided by the candidate."
                    if turns == 0
                    else "Evidence was partially demonstrated; depth and metrics should improve."
                ),
                "gaps": (
                    "Panel could not evaluate this competency due to missing behavioral examples."
                    if turns == 0
                    else "Needs clearer STAR structure, decisions, and measurable outcomes."
                ),
                "improvement": "Answer with one STAR example, including concrete actions, constraints, and quantifiable results.",
            })

        panel_summary = (
            "Insufficient evidence to assess performance. Candidate responses did not include usable behavioral examples."
            if turns == 0
            else "Performance was mixed. Some evidence was present, but stronger STAR depth and measurable impact are needed."
        )
        next_best_question = "Describe a specific high-stakes case using STAR and include measurable impact."
        return {
            "role": role,
            "overall_readiness_0_to_100": int(max(0, min(100, readiness))),
            "competencies": competencies,
            "panel_summary": panel_summary,
            "next_best_question": next_best_question,
        }

    @classmethod
    def _postprocess_cbi_output(
        cls,
        text: str,
        request: ChatCompletionRequest,
        request_messages: list[MessageInput],
    ) -> str:
        if request.addon_id != "competency_interview_coach":
            return text
        processed = cls._calibrate_cbi_scorecard(text, request, request_messages)
        if "CBI_SCORECARD_JSON:" not in processed and cls._is_cbi_report_request(request_messages):
            generated = cls._build_generated_cbi_scorecard(request, request_messages)
            block = "CBI_SCORECARD_JSON:" + json.dumps(generated, ensure_ascii=True, separators=(",", ":"))
            return f"{processed.strip()}\n\n{block}".strip()
        return processed

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        # OpenAI/vLLM style
        choices = response.get("choices")
        if choices and isinstance(choices, list) and len(choices) > 0:
            message = choices[0].get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip()

        # Ollama style
        message = response.get("message", {})
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
        alt = response.get("response")
        if isinstance(alt, str):
            return alt.strip()
        return ""

    @staticmethod
    def _is_fallback_error(error: Exception) -> bool:
        message = str(error).lower()
        if isinstance(error, TimeoutError):
            return True
        if isinstance(error, InferenceError):
            return True
        if any(marker in message for marker in OOM_MARKERS):
            return True
        if "ollama stream http error" in message or "vllm stream http error" in message:
            return True
        if "unknown model" in message:
            return True
        return "model" in message and "not found" in message

    def _persist_if_needed(self, request: ChatCompletionRequest, assistant_text: str, used_model_id: str) -> None:
        if not request.chat_id:
            return

        chat = self.repository.get_chat(request.chat_id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")

        if request.regenerate_target_message_id:
            replaced = self.repository.replace_assistant_message(
                chat_id=request.chat_id,
                message_id=request.regenerate_target_message_id,
                content=assistant_text,
                model_id=used_model_id,
            )
            if replaced:
                return

        last_user = next((msg for msg in reversed(request.messages) if msg.role == "user"), None)
        if last_user and chat.title.startswith("New Chat"):
            new_title = self._summarize_title(last_user.content)
            if new_title:
                self.repository.update_chat(chat.id, title=new_title, selected_model_id=None)

        if last_user:
            chat_latest = chat.messages[-1] if chat.messages else None
            if not chat_latest or chat_latest.role != "user" or chat_latest.content != last_user.content:
                self.repository.add_message(request.chat_id, "user", last_user.content, None)

        self.repository.add_message(request.chat_id, "assistant", assistant_text, used_model_id)

    def _checkpoint_chat_memory(self, chat_id: str | None, telemetry: dict[str, Any]) -> None:
        if not chat_id:
            return
        active_tokens = int(telemetry.get("active_input_tokens") or 0)
        memory = self.repository.get_chat_memory(chat_id)
        if memory:
            summary_text = str(memory.get("summary_text", ""))
            summary_version = int(memory.get("summary_version", 0))
            compaction_count = int(memory.get("compaction_count", 0))
            last_compacted_message_id = memory.get("last_compacted_message_id")
        else:
            summary_text = ""
            summary_version = 0
            compaction_count = 0
            last_compacted_message_id = None
        self.repository.upsert_chat_memory(
            chat_id=chat_id,
            summary_text=summary_text,
            summary_version=summary_version,
            compaction_count=compaction_count,
            last_compacted_message_id=last_compacted_message_id,
            token_estimate=active_tokens,
        )

    @staticmethod
    def _summarize_title(prompt: str) -> str:
        cleaned = " ".join(prompt.strip().split())
        if not cleaned:
            return "Untitled Chat"

        lowered = cleaned.lower()
        for prefix in ("please ", "can you ", "could you ", "i need ", "help me "):
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                lowered = cleaned.lower()
                break

        corrected_words = [COMMON_TYPOS.get(word.lower(), word) for word in cleaned.split(" ")]
        cleaned = " ".join(corrected_words)

        max_len = 58
        if len(cleaned) <= max_len:
            return cleaned[0].upper() + cleaned[1:]

        truncated = cleaned[:max_len].rstrip(" ,.;:-")
        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        return f"{truncated}..."

    async def complete(self, request: ChatCompletionRequest) -> CompletionResult:
        if not request.messages:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="messages cannot be empty")

        requested_model_id = self._resolve_model_id(request)
        compaction_telemetry: dict[str, Any] = {}
        if request.chat_id:
            compaction_event = self._maybe_compact_chat_context(
                chat_id=request.chat_id,
                requested_model_id=requested_model_id,
            )
            if compaction_event:
                compaction_telemetry = compaction_event

        request_messages, memory_prompt = self._build_request_messages(request)
        chain = self.model_registry.build_fallback_chain(requested_model_id)
        latest_query = self._latest_user_query(request_messages)
        addon_prompt = None
        if self.addon_store:
            addon_prompt = self.addon_store.system_prompt_for(request.addon_id)
        web_prompt = await self._build_web_context(latest_query) if request.web_mode else None
        interview_prompt = self._build_interview_context(request, latest_query)
        prompt_parts = [part for part in [addon_prompt, web_prompt, interview_prompt] if part]
        addon_prompt = "\n\n".join(prompt_parts) if prompt_parts else None
        attachment_prompt = self._build_attachment_prompt(request.attachment_upload_ids)

        attempted: list[str] = []
        fallback_reason: str | None = None
        last_telemetry: dict[str, Any] = {}

        for model_id in chain:
            attempted.append(model_id)
            profile = self.model_registry.get(model_id)
            allow_system_messages = self._supports_system_role(profile.runtime.model_ref)
            temperature, max_tokens = self._resolve_generation_controls(request, profile.limits.max_output_tokens)
            context_ceiling = self._effective_context_ceiling(request, profile.limits.max_context_tokens)
            if request.addon_id == "competency_interview_coach":
                max_tokens = min(max_tokens, CBI_MAX_OUTPUT_TOKENS)
            runtime_messages = self._as_runtime_messages(
                request_messages,
                response_length=request.response_length,
                thinking_level=request.thinking_level,
                memory_prompt=memory_prompt,
                addon_prompt=addon_prompt,
                attachment_prompt=attachment_prompt,
                allow_system_messages=allow_system_messages,
            )
            runtime_messages, telemetry = self._enforce_context_budget(
                runtime_messages,
                context_ceiling=context_ceiling,
                max_tokens=max_tokens,
            )
            telemetry.update(compaction_telemetry)
            last_telemetry = telemetry

            try:
                response = await self.inference_client.chat(
                    model_ref=profile.runtime.model_ref,
                    messages=runtime_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                usage_source = response
                text = self._extract_text(response)
                text = self._postprocess_cbi_output(text, request, request_messages)
                if not text:
                    retry_messages = self._as_runtime_messages(
                        request_messages,
                        response_length=request.response_length,
                        thinking_level=request.thinking_level,
                        memory_prompt=memory_prompt,
                        allow_system_messages=allow_system_messages,
                    )
                    retry_messages, retry_telemetry = self._enforce_context_budget(
                        retry_messages,
                        context_ceiling=context_ceiling,
                        max_tokens=max(64, max_tokens),
                    )
                    retry_telemetry.update(compaction_telemetry)
                    last_telemetry = retry_telemetry
                    retry_response = await self.inference_client.chat(
                        model_ref=profile.runtime.model_ref,
                        messages=retry_messages,
                        temperature=temperature,
                        max_tokens=max(64, max_tokens),
                    )
                    usage_source = retry_response
                    text = self._extract_text(retry_response)
                    text = self._postprocess_cbi_output(text, request, request_messages)
                    if not text:
                        fallback_reason = "Empty output from model"
                        continue
                usage = {
                    "prompt_tokens": usage_source.get("prompt_eval_count") or usage_source.get("usage", {}).get("prompt_tokens"),
                    "completion_tokens": usage_source.get("eval_count") or usage_source.get("usage", {}).get("completion_tokens"),
                    "total_tokens": (
                        (usage_source.get("prompt_eval_count") or usage_source.get("usage", {}).get("prompt_tokens") or 0)
                        + (usage_source.get("eval_count") or usage_source.get("usage", {}).get("completion_tokens") or 0)
                    ),
                }
                self._persist_if_needed(request, text, model_id)
                self._checkpoint_chat_memory(request.chat_id, last_telemetry)
                return CompletionResult(
                    text=text,
                    used_model_id=model_id,
                    fallback_reason=fallback_reason,
                    usage=usage,
                    attempted_models=attempted,
                    telemetry=last_telemetry,
                )
            except (InferenceError, TimeoutError) as error:
                if self._is_fallback_error(error):
                    fallback_reason = str(error)
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Inference failed: {error}",
                ) from error

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All model attempts failed",
        )

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, Any]]:
        if not request.messages:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="messages cannot be empty")

        requested_model_id = self._resolve_model_id(request)
        compaction_telemetry: dict[str, Any] = {}
        if request.chat_id:
            compaction_event = self._maybe_compact_chat_context(
                chat_id=request.chat_id,
                requested_model_id=requested_model_id,
            )
            if compaction_event:
                compaction_telemetry = compaction_event

        request_messages, memory_prompt = self._build_request_messages(request)
        chain = self.model_registry.build_fallback_chain(requested_model_id)
        latest_query = self._latest_user_query(request_messages)
        addon_prompt = None
        if self.addon_store:
            addon_prompt = self.addon_store.system_prompt_for(request.addon_id)
        web_prompt = await self._build_web_context(latest_query) if request.web_mode else None
        interview_prompt = self._build_interview_context(request, latest_query)
        prompt_parts = [part for part in [addon_prompt, web_prompt, interview_prompt] if part]
        addon_prompt = "\n\n".join(prompt_parts) if prompt_parts else None
        attachment_prompt = self._build_attachment_prompt(request.attachment_upload_ids)

        attempted: list[str] = []
        fallback_reason: str | None = None
        last_telemetry: dict[str, Any] = {}

        for model_id in chain:
            attempted.append(model_id)
            profile = self.model_registry.get(model_id)
            allow_system_messages = self._supports_system_role(profile.runtime.model_ref)
            temperature, max_tokens = self._resolve_generation_controls(request, profile.limits.max_output_tokens)
            context_ceiling = self._effective_context_ceiling(request, profile.limits.max_context_tokens)
            if request.addon_id == "competency_interview_coach":
                max_tokens = min(max_tokens, CBI_MAX_OUTPUT_TOKENS)
            runtime_messages = self._as_runtime_messages(
                request_messages,
                response_length=request.response_length,
                thinking_level=request.thinking_level,
                memory_prompt=memory_prompt,
                addon_prompt=addon_prompt,
                attachment_prompt=attachment_prompt,
                allow_system_messages=allow_system_messages,
            )
            runtime_messages, telemetry = self._enforce_context_budget(
                runtime_messages,
                context_ceiling=context_ceiling,
                max_tokens=max_tokens,
            )
            telemetry.update(compaction_telemetry)
            last_telemetry = telemetry
            assistant_text = ""
            usage: dict[str, int | None] = {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            }

            try:
                if request.addon_id == "competency_interview_coach":
                    buffered = await self.inference_client.chat(
                        model_ref=profile.runtime.model_ref,
                        messages=runtime_messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    assistant_text = self._extract_text(buffered)
                    assistant_text = self._postprocess_cbi_output(assistant_text, request, request_messages)
                    if not assistant_text.strip():
                        fallback_reason = "Empty output from model"
                        continue
                    usage = {
                        "prompt_tokens": buffered.get("prompt_eval_count") or buffered.get("usage", {}).get("prompt_tokens"),
                        "completion_tokens": buffered.get("eval_count") or buffered.get("usage", {}).get("completion_tokens"),
                        "total_tokens": (
                            (buffered.get("prompt_eval_count") or buffered.get("usage", {}).get("prompt_tokens") or 0)
                            + (buffered.get("eval_count") or buffered.get("usage", {}).get("completion_tokens") or 0)
                        ),
                    }
                    yield {
                        "type": "token",
                        "token": assistant_text,
                        "used_model_id": model_id,
                    }
                    self._persist_if_needed(request, assistant_text, model_id)
                    self._checkpoint_chat_memory(request.chat_id, last_telemetry)
                    yield {
                        "type": "done",
                        "used_model_id": model_id,
                        "fallback_reason": fallback_reason,
                        "attempted_models": attempted,
                        "usage": usage,
                        "telemetry": last_telemetry,
                        "created": int(time.time()),
                    }
                    return

                async for chunk in self.inference_client.stream_chat(
                    model_ref=profile.runtime.model_ref,
                    messages=runtime_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    content = ""
                    # Ollama style
                    content = str(chunk.get("message", {}).get("content", ""))
                    # OpenAI/vLLM style
                    choices = chunk.get("choices")
                    if choices and isinstance(choices, list) and len(choices) > 0:
                        delta = choices[0].get("delta", {})
                        if "content" in delta:
                            content = str(delta["content"])

                    if content:
                        assistant_text += content
                        yield {
                            "type": "token",
                            "token": content,
                            "used_model_id": model_id,
                        }

                    # Usage handling
                    if chunk.get("done") or choices and choices[0].get("finish_reason"):
                        usage = {
                            "prompt_tokens": chunk.get("prompt_eval_count") or chunk.get("usage", {}).get("prompt_tokens"),
                            "completion_tokens": chunk.get("eval_count") or chunk.get("usage", {}).get("completion_tokens"),
                            "total_tokens": (
                                (chunk.get("prompt_eval_count") or chunk.get("usage", {}).get("prompt_tokens") or 0)
                                + (chunk.get("eval_count") or chunk.get("usage", {}).get("completion_tokens") or 0)
                            ),
                        }

                if not assistant_text.strip():
                    retry_messages = self._as_runtime_messages(
                        request_messages,
                        response_length=request.response_length,
                        thinking_level=request.thinking_level,
                        memory_prompt=memory_prompt,
                        allow_system_messages=allow_system_messages,
                    )
                    retry_messages, retry_telemetry = self._enforce_context_budget(
                        retry_messages,
                        context_ceiling=context_ceiling,
                        max_tokens=max(64, max_tokens),
                    )
                    retry_telemetry.update(compaction_telemetry)
                    last_telemetry = retry_telemetry
                    retry_response = await self.inference_client.chat(
                        model_ref=profile.runtime.model_ref,
                        messages=retry_messages,
                        temperature=temperature,
                        max_tokens=max(64, max_tokens),
                    )
                    retry_text = self._extract_text(retry_response)
                    if retry_text:
                        retry_text = self._postprocess_cbi_output(retry_text, request, request_messages)
                        assistant_text = retry_text
                        usage = {
                            "prompt_tokens": retry_response.get("prompt_eval_count"),
                            "completion_tokens": retry_response.get("eval_count"),
                            "total_tokens": (
                                (retry_response.get("prompt_eval_count") or 0)
                                + (retry_response.get("eval_count") or 0)
                            ),
                        }
                        yield {
                            "type": "token",
                            "token": retry_text,
                            "used_model_id": model_id,
                        }
                    else:
                        fallback_reason = "Empty output from model"
                        continue

                self._persist_if_needed(request, assistant_text, model_id)
                self._checkpoint_chat_memory(request.chat_id, last_telemetry)
                yield {
                    "type": "done",
                    "used_model_id": model_id,
                    "fallback_reason": fallback_reason,
                    "attempted_models": attempted,
                    "usage": usage,
                    "telemetry": last_telemetry,
                    "created": int(time.time()),
                }
                return
            except (InferenceError, TimeoutError) as error:
                if self._is_fallback_error(error):
                    fallback_reason = str(error)
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Inference failed: {error}",
                ) from error

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="All model attempts failed",
        )
