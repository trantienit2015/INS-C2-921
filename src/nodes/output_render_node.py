"""AgentCore Platform v1.0"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

_VALID_TRANSFORM_TYPES = {"verbatim", "field_extract", "date_normalize"}


class OutputRenderNode(FunctionNode):
    """Step 5 — assembles the final formatted output and hosts the S-3
    deterministic citation-preservation gate (fail-safe).

    The preservation gate lives in `_extra_security_gate_output()` (runs
    automatically after `execute()` via the framework's `@final` S-3 method)
    and rejects the WHOLE package (`status = FAILED`) if any checklist item
    or summary segment carries an unmapped/invalid evidence claim, or if a
    required evidence category has no valid claim — it never silently drops
    an item.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Defense-in-depth: outer route() normally skips post_process on an
        # upstream ERROR, but re-check the precondition rather than trust it
        # (see RouteRenderNode's same guard for the inner-chain equivalent).
        if state.get("status") == AgentStatus.ERROR.value or not state.get("checklist_items"):
            emit_trace_event("cancellation_evidence_package_rejected", {"reason": "no_checklist_upstream"}, state)
            return {"status": AgentStatus.ERROR.value, "error_log": ["OutputRenderNode: no checklist to render"]}

        checklist_items = state.get("checklist_items", [])
        summary_segments = state.get("customer_notice_evidence_summary_segments", [])
        route = state.get("human_review_route", {})

        formatted_output = {
            "checklist_items": checklist_items,
            "customer_notice_evidence_summary_segments": summary_segments,
            "human_review_route": route,
        }

        emit_trace_event(
            "cancellation_evidence_package_rendered",
            {"correlation_id": state.get("correlation_id"), "item_count": len(checklist_items)},
            state,
        )

        # Echo the fields the S-3 hook below re-checks — own-dict self-consistency
        # (S-3: re-check the key THIS node's execute()
        # actually returns, not an upstream state.get()).
        return {
            "formatted_output": formatted_output,
            "checklist_items": checklist_items,
            "customer_notice_evidence_summary_segments": summary_segments,
            "retrieved_passages": state.get("retrieved_passages", []),
            "required_evidence_categories": state.get("required_evidence_categories", []),
            "human_review_route": route,
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """S-3 preservation-variant gate: verify every evidence claim, fail-safe.

        Never raises; always returns a dict. Rejects the whole package
        (`status = ERROR`) rather than silently dropping an unsupported claim.
        """
        passage_index = {p.get("passage_id"): p for p in state.get("retrieved_passages", [])}
        required_categories = set(state.get("required_evidence_categories", []))
        covered_categories: set[str] = set()

        claims = list(state.get("checklist_items", [])) + list(
            state.get("customer_notice_evidence_summary_segments", [])
        )
        for claim in claims:
            passage = passage_index.get(claim.get("passage_id"))
            if passage is None:
                return self._reject("unmapped claim_id/passage_id: " + str(claim.get("claim_id")))
            if claim.get("procedure_version") != passage.get("procedure_version"):
                return self._reject("procedure_version mismatch for claim: " + str(claim.get("claim_id")))
            transform_type = claim.get("transform_type")
            if transform_type not in _VALID_TRANSFORM_TYPES:
                return self._reject("unknown transform_type for claim: " + str(claim.get("claim_id")))
            source_span = claim.get("source_span") or ""
            if not source_span:
                return self._reject("empty source_span for claim: " + str(claim.get("claim_id")))
            if transform_type == "verbatim" and source_span not in (passage.get("text") or ""):
                return self._reject("source_span not verbatim-verifiable for claim: " + str(claim.get("claim_id")))
            category = claim.get("required_category")
            if category:
                covered_categories.add(category)

        missing = required_categories - covered_categories
        if missing:
            return self._reject("missing required_evidence_categories: " + ", ".join(sorted(missing)))

        return state

    @staticmethod
    def _reject(reason: str) -> dict[str, Any]:
        return {"status": AgentStatus.ERROR.value, "error_log": [f"OutputRenderNode S-3 preservation gate: {reason}"]}
