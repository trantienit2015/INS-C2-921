"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.

from typing import NotRequired

from framework.schemas.agent_state import AgentState


# Type-check note: the wheel ships no py.typed, so mypy resolves AgentState to Any
# and reports every NotRequired below as valid-type. The fields are correct (the state
# contract requires NotRequired) -- the report is a packaging artifact, suppressed per field.
# Drop these ignores once the wheel ships py.typed.
class State(AgentState):
    """Agent state for INS-C2-921 (cancellation-notice evidence draft pipeline).

    Add only fields specific to this agent below. All shared fields
    (user_input, status, session_id, node_history, error_log, validated_input,
    hitl_*, etc.) are inherited from AgentState.
    """

    # ProcedureRetrieve output (inner) — ranked procedure/policy passages with passage_id
    retrieved_passages: NotRequired[list[dict]]  # type: ignore[valid-type]

    # ChecklistDraft output (inner) — cited checklist items + fixed category manifest
    required_evidence_categories: NotRequired[list[str]]  # type: ignore[valid-type]
    checklist_items: NotRequired[list[dict]]  # type: ignore[valid-type]
    customer_notice_evidence_summary_segments: NotRequired[list[dict]]  # type: ignore[valid-type]

    # RouteRender output (inner) — assembled human-review route
    human_review_route: NotRequired[dict]  # type: ignore[valid-type]
