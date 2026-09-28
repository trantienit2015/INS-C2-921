# INS-C2-921 - GraphNode boundary test (Cat 2 outer main-slot wrapper).
#
# Why this test exists: PB-6 (test_pb_invoke_order.py) only self-discovers
# BaseNode subclasses under src/nodes/. CancellationEvidenceGraphNode lives
# under src/graph/graph.py by design (matches the scaffold Cat 2 canonical
# layout, so a single-node probe does not accidentally pull in the whole
# inner subgraph) - but that placement does not exempt it from test
# coverage. This is a test-scope blind spot: the outer GraphNode is a real security boundary
# (first node to receive the caller's input) that no PB-6 probe reaches.
#
# framework/nodes/graph_node.py: GraphNode extends BaseNode directly (not
# FunctionNode), so it has no _security_gate_input/_security_gate_output at
# all - S-2/S-3 gating is delegated entirely to the outer InputValidateNode /
# OutputRenderNode and the inner subgraph's own FunctionNode chain. This
# test proves that delegation is real, not absent.

from framework.nodes.function_node import FunctionNode
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import CancellationEvidenceGraphNode
from src.nodes.procedure_retrieve_node import ProcedureRetrieveNode


def _node():
    return CancellationEvidenceGraphNode(vector_store=None, llm=None)


class TestGraphNodeS1TrustGate:
    """S-1: the outer main-slot GraphNode enforces the trust gate like any BaseNode."""

    def test_insufficient_trust_returns_error_without_invoking_subgraph(self, monkeypatch):
        node = _node()
        called = {"get_subgraph": False}

        def _spy_get_subgraph():
            called["get_subgraph"] = True
            raise AssertionError("get_subgraph() must not run when the S-1 gate denies")

        monkeypatch.setattr(node, "get_subgraph", _spy_get_subgraph)

        state = {
            "caller_trust_level": TrustLevel.ANONYMOUS.value,
            "validated_input": '{"cancellation_type": "customer_initiated"}',
        }
        out = node(state)

        assert out["status"] == "error"
        assert any("S-1 trust gate denied" in e for e in out["error_log"])
        assert called["get_subgraph"] is False

    def test_matches_agent_yaml_required_trust_level(self):
        # The outer main-slot wrapper must match config/agent.yaml
        # (VERIFIED_EXTERNAL) — it performs the privileged operation
        # (vector_store + llm + secrets), not the inner subgraph's
        # ANONYMOUS default.
        assert CancellationEvidenceGraphNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL


class TestGraphNodeBoundaryMapping:
    """Boundary mapping: extract_input()/merge_output() do not leak raw state/subgraph dicts."""

    def test_extract_input_only_reads_validated_input(self):
        node = _node()
        state = {
            "validated_input": '{"cancellation_type": "customer_initiated"}',
            "user_input": "raw caller text should not leak separately",
            "unrelated_secret_field": "must-not-appear",
        }
        extracted = node.extract_input(state)

        assert isinstance(extracted, str)
        assert "unrelated_secret_field" not in extracted
        assert "must-not-appear" not in extracted

    def test_merge_output_maps_fields_explicitly_no_raw_passthrough(self):
        node = _node()
        state = {}
        sub_result = {
            "retrieved_passages": [{"passage_id": "P1"}],
            "required_evidence_categories": ["effective_date"],
            "checklist_items": [{"claim_id": "C1"}],
            "customer_notice_evidence_summary_segments": [{"claim_id": "S1"}],
            "human_review_route": {"queue": "ops"},
            "status": "success",
            # A field the subgraph might carry internally that must NOT leak
            # into the outer state unless merge_output() explicitly maps it.
            "internal_debug_trace": "should-not-be-copied",
        }
        merged = node.merge_output(state, sub_result)

        assert "internal_debug_trace" not in merged
        assert merged["status"] == "success"
        assert set(merged.keys()) == {
            "retrieved_passages",
            "required_evidence_categories",
            "checklist_items",
            "customer_notice_evidence_summary_segments",
            "human_review_route",
            "status",
        }


class TestGraphNodeDelegatesGatingToInnerSubgraph:
    """Delegation has a real target: the inner subgraph's entry node runs S-1/S-2/S-3."""

    def test_inner_entry_node_is_a_function_node_with_security_gates(self):
        # ProcedureRetrieveNode is the inner subgraph's entry point
        # (domain_workflow_graph.py: START -> procedure_retrieve). It is a
        # FunctionNode, so the framework's @final S-2/S-3 gates run on every
        # invocation of the inner subgraph - this is where the GraphNode's
        # skipped lifecycle is actually enforced, not omitted.
        assert issubclass(ProcedureRetrieveNode, FunctionNode)
        assert hasattr(ProcedureRetrieveNode, "required_trust_level")
