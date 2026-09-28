"""AgentCore Platform v1.0"""

# INS-C2-921 — Insurance Policy Cancellation Notice Evidence Draft Agent
# Cat 2 outer graph: fixed AgentBaseGraph backbone + GraphNode `main` slot
# wrapping the CancellationEvidenceWorkflowGraph inner subgraph
# (src/graph/domain_workflow_graph.py).

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.nodes.input_validate_node import InputValidateNode
from src.nodes.output_render_node import OutputRenderNode
from src.schemas.state import State


class CancellationEvidenceGraphNode(GraphNode):
    """Wraps the inner cancellation-evidence workflow; assigned to `main`.

    NOTE: this class lives HERE, in
    src/graph/graph.py, NOT under src/nodes/ — tests/proof_of_boundary/
    test_pb_invoke_order.py auto-discovers every BaseNode subclass under
    src/nodes/ and asserts the standard S-1->S-4->S-2->execute->S-3->S-4
    lifecycle, which GraphNode intentionally does not run (it delegates
    security gating to the inner subgraph). Boundary coverage for this
    class lives in tests/proof_of_boundary/test_pb_graphnode_boundary.py.
    """

    # S-1: outer main-slot wrapper — first node in the outer
    # backbone receiving caller input; matches config/agent.yaml
    # required_trust_level and the sibling outer FunctionNodes
    # (InputValidateNode / OutputRenderNode).
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(
        self,
        vector_store: Any = None,
        llm: Any = None,
        procedure_version: str = "v1",
        top_k: int = 6,
        escalation_directory: dict[str, Any] | None = None,
        required_evidence_categories: list[str] | None = None,
    ):
        super().__init__()
        self._vector_store = vector_store
        self._llm = llm
        self._procedure_version = procedure_version
        self._top_k = top_k
        self._escalation_directory = escalation_directory
        self._required_evidence_categories = required_evidence_categories

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import CancellationEvidenceWorkflowGraph

        sg = CancellationEvidenceWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        # The outer pre_process -> main edge is unconditional (AgentBaseGraph
        # only gates on status AFTER main, via route()) — an InputValidateNode
        # S-1/S-2 rejection still dispatches here. Re-check the precondition
        # instead of trusting the edge to have gated it: an empty string makes the inner
        # ProcedureRetrieveNode fail closed immediately.
        if str(state.get("status", "")).lower().endswith("error"):
            emit_trace_event(
                "cancellation_evidence_dispatch_skipped", {"correlation_id": state.get("correlation_id")}, state
            )
            return ""
        # S-4: runs inside GraphNode.execute() — audit dispatch into the inner subgraph.
        emit_trace_event("cancellation_evidence_dispatched", {"correlation_id": state.get("correlation_id")}, state)
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        # S-4: runs inside GraphNode.execute() — audit the subgraph outcome merged back out.
        emit_trace_event(
            "cancellation_evidence_completed",
            {"correlation_id": state.get("correlation_id"), "item_count": len(sub_result.get("checklist_items", []))},
            state,
        )
        return {
            "retrieved_passages": sub_result.get("retrieved_passages", []),
            "required_evidence_categories": sub_result.get("required_evidence_categories", []),
            "checklist_items": sub_result.get("checklist_items", []),
            "customer_notice_evidence_summary_segments": sub_result.get(
                "customer_notice_evidence_summary_segments", []
            ),
            "human_review_route": sub_result.get("human_review_route", {}),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {
            "vector_store": self._vector_store,
            "llm": self._llm,
            "procedure_version": self._procedure_version,
            "top_k": self._top_k,
            "escalation_directory": self._escalation_directory,
            "required_evidence_categories": self._required_evidence_categories,
        }


class InsC2921CancellationNoticeEvidenceDraftAgent(AgentBaseGraph):
    """Outer graph — Cat 2, fixed backbone: initialize -> pre_process ->
    main (GraphNode) -> post_process -> finalize.
    """

    @property
    def name(self) -> str:
        return "ins-c2-921"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode
        self._nodes["pre_process"] = InputValidateNode()
        self._nodes["main"] = CancellationEvidenceGraphNode(
            vector_store=self.config.get("vector_store"),
            llm=self.config.get("llm"),
            procedure_version=self.config.get("procedure_version", "v1"),
            top_k=self.config.get("top_k", 6),
            escalation_directory=self.config.get("escalation_directory"),
            required_evidence_categories=self.config.get("required_evidence_categories"),
        )
        self._nodes["post_process"] = OutputRenderNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.


Graph = InsC2921CancellationNoticeEvidenceDraftAgent  # alias for agent.yaml module:"src.graph"
