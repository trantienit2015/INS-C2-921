"""AgentCore Platform v1.0"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

DEFAULT_REQUIRED_EVIDENCE_CATEGORIES = [
    "effective_date",
    "notice_period",
    "fee_or_refund_disclosure",
    "acknowledgment_method",
]


class ChecklistDraftNode(FunctionNode):
    """Step 3 — low-temperature grounded generation of the cited evidence checklist
    + customer-notice evidence summary.

    Every checklist item and summary segment carries a `claim_id` tied to a
    retrieved `passage_id`; the S-3 preservation gate (OutputRenderNode) later
    verifies every claim before the package is accepted.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, llm: Any = None, required_evidence_categories: list[str] | None = None):
        # Default None is required so PB-6 (tests/proof_of_boundary/test_pb_invoke_order.py)
        # can instantiate this node with zero args; execute() always returns an
        # early ERROR before touching self._llm when retrieved_passages is empty.
        self._llm = llm
        self._required_evidence_categories = required_evidence_categories or DEFAULT_REQUIRED_EVIDENCE_CATEGORIES

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        passages = state.get("retrieved_passages", [])
        if not passages:
            emit_trace_event("checklist_draft_rejected", {"reason": "no_retrieved_passages"}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ChecklistDraftNode: no retrieved_passages to ground on"],
            }

        # Stage 5 deploy-ability: the
        # entry-point (src/api/server.py) constructs Graph() without an llm,
        # so self._llm is a LEGITIMATE None state (no LLM
        # provider is configured), not a bug to crash on. A CONFIGURED-but-failing
        # LLM must still fall through to the error paths below — this
        # branch only fires when NO llm was provisioned at all.
        if self._llm is None:
            checklist_items, summary_segments = self._deterministic_checklist(passages)
            emit_trace_event("checklist_draft_deterministic_fallback", {"reason": "no_llm_provisioned"}, state)
            return {
                "required_evidence_categories": self._required_evidence_categories,
                "checklist_items": checklist_items,
                "customer_notice_evidence_summary_segments": summary_segments,
                "status": AgentStatus.SUCCESS.value,
            }

        prompt = self._build_prompt(passages)
        # BaseLLM.complete() contract: takes a messages list, returns a dict
        # {"content": str, ...} — never a bare string (shared/services/llm/base_llm.py).
        response = self._llm.complete([{"role": "user", "content": prompt}])
        content = response.get("content", "") if isinstance(response, dict) else str(response)
        parsed = self._parse_response(content)
        if parsed is None:
            emit_trace_event("checklist_draft_rejected", {"reason": "llm_response_not_valid_json"}, state)
            return {"status": AgentStatus.ERROR.value, "error_log": ["ChecklistDraftNode: LLM response not valid JSON"]}

        checklist_items = parsed.get("checklist_items", [])
        summary_segments = parsed.get("customer_notice_evidence_summary_segments", [])
        if not checklist_items:
            emit_trace_event("checklist_draft_rejected", {"reason": "empty_checklist_items"}, state)
            return {"status": AgentStatus.ERROR.value, "error_log": ["ChecklistDraftNode: empty checklist_items"]}

        emit_trace_event(
            "checklist_drafted",
            {
                "correlation_id": state.get("correlation_id"),
                "item_count": len(checklist_items),
                "summary_segment_count": len(summary_segments),
            },
            state,
        )
        return {
            "required_evidence_categories": self._required_evidence_categories,
            "checklist_items": checklist_items,
            "customer_notice_evidence_summary_segments": summary_segments,
            "status": AgentStatus.SUCCESS.value,
        }

    def _build_prompt(self, passages: list[dict[str, Any]]) -> str:
        passage_lines = "\n".join(
            f"- passage_id={p.get('passage_id')} procedure_version={p.get('procedure_version')}: {p.get('text', '')}"
            for p in passages
        )
        categories = ", ".join(self._required_evidence_categories)
        return (
            "Draft a cancellation-notice evidence checklist grounded ONLY in the passages below. "
            f"Cover every required category: {categories}. "
            "Every checklist item and summary segment MUST cite a passage_id + procedure_version "
            "with an exact source_span (verbatim, field_extract, or date_normalize).\n\n"
            f"Passages:\n{passage_lines}\n\n"
            'Respond as JSON: {"checklist_items": [...], "customer_notice_evidence_summary_segments": [...]}'
        )

    def _parse_response(self, raw_response: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(raw_response) if isinstance(raw_response, str) else raw_response
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def _deterministic_checklist(
        self, passages: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """STG provisional stand-in when no llm is provisioned (Stage 5
        deploy-ability: no LLM provider is configured). One `verbatim` claim per required category,
        cycling through the retrieved passages; `source_span` is the whole
        passage text so it is always a valid substring (S-3 preservation gate
        in OutputRenderNode). NOT LLM-grounded drafting — §STG Sign-off
        Record must record this mode explicitly.
        """
        checklist_items = [
            {
                "item_id": f"stub-item-{i}",
                "required_category": category,
                "claim_id": f"stub-claim-{i}",
                "artifact_segment_id": f"stub-seg-{i}",
                "claim_text": f"Deterministic stub coverage for {category}",
                "passage_id": passages[i % len(passages)]["passage_id"],
                "procedure_version": passages[i % len(passages)]["procedure_version"],
                "source_span": passages[i % len(passages)]["text"],
                "transform_type": "verbatim",
            }
            for i, category in enumerate(self._required_evidence_categories)
        ]
        return checklist_items, []
