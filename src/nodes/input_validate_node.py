"""AgentCore Platform v1.0"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.service import has_credential_leak


class InputValidateNode(FunctionNode):
    """Step 1 — S-1 trust gate + S-2 deterministic input scan.

    Rejects regulated policyholder-identifier / credential patterns before any
    retrieval happens. Passes sanitized,
    JSON-serialized request metadata downstream via `validated_input` for the
    inner subgraph.
    """

    # S-1: outer boundary node — matches config/agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = state.get("user_input", "")

        if not user_input or not str(user_input).strip():
            emit_trace_event("input_validate_rejected", {"reason": "empty_user_input"}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["InputValidateNode: user_input is empty or missing"],
            }

        # S-2 deterministic domain scan (My Number/policy-ID, Bearer/JWT, credential JSON).
        if has_credential_leak(user_input):
            emit_trace_event("input_validate_rejected", {"reason": "credential_or_pii_pattern"}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "InputValidateNode: request contains a regulated identifier or credential-shaped pattern"
                ],
            }

        try:
            request_metadata = json.loads(user_input) if isinstance(user_input, str) else user_input
        except (ValueError, TypeError):
            request_metadata = {"raw_request": str(user_input).strip()}
        if not isinstance(request_metadata, dict):
            request_metadata = {"raw_request": request_metadata}

        emit_trace_event(
            "cancellation_request_validated",
            {"correlation_id": state.get("correlation_id"), "field_count": len(request_metadata)},
            state,
        )

        return {
            "validated_input": json.dumps(request_metadata, ensure_ascii=False),
            "status": AgentStatus.SUCCESS.value,
        }
