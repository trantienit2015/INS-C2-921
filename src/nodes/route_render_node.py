"""AgentCore Platform v1.0"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.escalation_directory import resolve_route


class RouteRenderNode(FunctionNode):
    """Step 4 — assembles the cited draft + resolves the human-review queue
    via a deterministic escalation-directory lookup.
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, escalation_directory: dict[str, dict[str, Any]] | None = None):
        self._escalation_directory = escalation_directory or {}

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Inner subgraph edges are unconditional (langgraph add_edge, not
        # add_conditional_edges) — an upstream ERROR (procedure_retrieve /
        # checklist_draft) still dispatches here. Re-check the precondition
        # instead of trusting the edge to have gated it.
        if state.get("status") == AgentStatus.ERROR.value or not state.get("checklist_items"):
            emit_trace_event("human_review_route_skipped", {"reason": "no_checklist_upstream"}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["RouteRenderNode: skipped — no checklist drafted upstream"],
            }

        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            payload = {}
        cancellation_type = payload.get("cancellation_type", "") if isinstance(payload, dict) else ""

        route = resolve_route(cancellation_type, self._escalation_directory)

        emit_trace_event(
            "human_review_route_resolved",
            {"correlation_id": state.get("correlation_id"), "queue": route["queue"]},
            state,
        )
        return {"human_review_route": route, "status": AgentStatus.SUCCESS.value}
