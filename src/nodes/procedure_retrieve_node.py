"""AgentCore Platform v1.0"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.service import ProcedureRetrievalService


def _deterministic_passages(procedure_version: str) -> list[dict[str, Any]]:
    """STG provisional stand-in when no vector_store is provisioned (Stage 5
    deploy-ability: no KB/vector index is configured). Fixed, self-contained procedure text so
    ChecklistDraftNode can ground a valid, citeable checklist without a real
    KB. NOT real procedure content — replace once the platform provisions a
    vector_store.
    """
    return [
        {
            "passage_id": "stub-procedure-001",
            "procedure_version": procedure_version,
            "text": (
                "Cancellation takes effect 30 days after the notice is received. "
                "A processing fee of 2000 JPY applies for early cancellation. "
                "The customer must acknowledge the cancellation via a signed form."
            ),
        }
    ]


class ProcedureRetrieveNode(FunctionNode):
    """Step 2 — hybrid retrieval over the versioned internal procedures + policy-terms KB.

    Inner subgraph node — trust already authenticated at the outer backbone
    (InputValidateNode, VERIFIED_EXTERNAL).
    """

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def __init__(self, retrieval_service: ProcedureRetrievalService | None = None):
        # Default None is required so PB-6 (tests/proof_of_boundary/test_pb_invoke_order.py)
        # can instantiate this node with zero args; execute() always returns an
        # early ERROR before touching self._retrieval_service when user_input is
        # empty/invalid, so this is safe.
        self._retrieval_service = retrieval_service

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        raw = state.get("user_input", "")
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            payload = None
        if not isinstance(payload, dict):
            emit_trace_event("procedure_retrieve_rejected", {"reason": "invalid_inner_input"}, state)
            return {"status": AgentStatus.ERROR.value, "error_log": ["ProcedureRetrieveNode: invalid inner input"]}

        cancellation_type = payload.get("cancellation_type", "")
        query = payload.get("raw_request") or cancellation_type or json.dumps(payload, ensure_ascii=False)

        # Stage 5 deploy-ability: the entry-point
        # (src/api/server.py) constructs Graph() without a vector_store, so
        # self._retrieval_service.vector_store is a LEGITIMATE None state, not a
        # bug to crash on. Handle it explicitly with a deterministic fallback
        # instead of calling straight through to a None client.
        if self._retrieval_service is not None and self._retrieval_service.vector_store is not None:
            passages = self._retrieval_service.retrieve(query, cancellation_type=cancellation_type)
        else:
            passages = _deterministic_passages(
                self._retrieval_service.procedure_version if self._retrieval_service is not None else "v1"
            )
            emit_trace_event(
                "procedure_retrieve_deterministic_fallback", {"reason": "no_vector_store_provisioned"}, state
            )
        if not passages:
            emit_trace_event("procedure_retrieve_rejected", {"reason": "no_passages_retrieved"}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ProcedureRetrieveNode: no procedure passages retrieved"],
            }

        emit_trace_event(
            "procedure_passages_retrieved",
            {"correlation_id": state.get("correlation_id"), "passage_count": len(passages)},
            state,
        )
        return {"retrieved_passages": passages, "status": AgentStatus.SUCCESS.value}
