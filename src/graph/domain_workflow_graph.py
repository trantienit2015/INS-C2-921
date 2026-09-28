"""AgentCore Platform v1.0"""

# Inner graph for the Cat 2 cancellation-notice evidence-draft workflow.
# Instantiated by CancellationEvidenceGraphNode.get_subgraph() in graph.py.
# The outer/inner boundary contract: the outer GraphNode hands the inner graph a
# JSON string, and the inner graph returns its own fields for explicit merging.

from typing import Any
from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.checklist_draft_node import ChecklistDraftNode
from src.nodes.procedure_retrieve_node import ProcedureRetrieveNode
from src.nodes.route_render_node import RouteRenderNode
from src.schemas.state import State
from src.services.service import ProcedureRetrievalService


class CancellationEvidenceWorkflowGraph(BaseGraph):
    """Inner graph — ProcedureRetrieve -> ChecklistDraft -> RouteRender.

    Custom linear topology (BaseGraph directly, no pre/main/post slots).
    Called by CancellationEvidenceGraphNode.get_subgraph() in graph.py.
    """

    @property
    def name(self) -> str:
        return "cancellation_evidence_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        pass

    def register_nodes(self) -> None:
        cfg = self.config if hasattr(self, "config") else {}
        retrieval_service = ProcedureRetrievalService(
            vector_store=cfg.get("vector_store"),
            procedure_version=cfg.get("procedure_version", "v1"),
            top_k=cfg.get("top_k", 6),
        )
        self._nodes["procedure_retrieve"] = ProcedureRetrieveNode(retrieval_service=retrieval_service)
        self._nodes["checklist_draft"] = ChecklistDraftNode(
            llm=cfg.get("llm"),
            required_evidence_categories=cfg.get("required_evidence_categories"),
        )
        self._nodes["route_render"] = RouteRenderNode(escalation_directory=cfg.get("escalation_directory"))

    def add_edges(self) -> None:
        self._sg.add_edge(START, "procedure_retrieve")
        self._sg.add_edge("procedure_retrieve", "checklist_draft")
        self._sg.add_edge("checklist_draft", "route_render")
        self._sg.add_edge("route_render", END)

    def route(self, state: AgentState) -> str:
        return END if state.get("status") == AgentStatus.ERROR.value else "route_render"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "retrieved_passages": state.get("retrieved_passages", []),
            "required_evidence_categories": state.get("required_evidence_categories", []),
            "checklist_items": state.get("checklist_items", []),
            "customer_notice_evidence_summary_segments": state.get("customer_notice_evidence_summary_segments", []),
            "human_review_route": state.get("human_review_route", {}),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
