from framework.schemas.agent_status import AgentStatus

from src.nodes.output_render_node import OutputRenderNode

PASSAGES = [{"passage_id": "p1", "procedure_version": "v1", "text": "Cancellation takes effect 30 days after notice."}]
VALID_CLAIM = {
    "item_id": "i1",
    "required_category": "notice_period",
    "claim_id": "c1",
    "passage_id": "p1",
    "procedure_version": "v1",
    "source_span": "Cancellation takes effect 30 days after notice.",
    "transform_type": "verbatim",
}


class TestOutputRenderNode:
    def test_execute_assembles_formatted_output(self):
        node = OutputRenderNode()
        out = node.execute(
            {
                "checklist_items": [VALID_CLAIM],
                "customer_notice_evidence_summary_segments": [],
                "human_review_route": {"queue": "q", "escalation_contact": "c"},
                "retrieved_passages": PASSAGES,
                "required_evidence_categories": ["notice_period"],
            }
        )
        assert out["status"] == AgentStatus.SUCCESS
        assert out["formatted_output"]["human_review_route"]["queue"] == "q"

    def test_execute_short_circuits_on_upstream_error(self):
        node = OutputRenderNode()
        out = node.execute({"status": AgentStatus.ERROR, "checklist_items": []})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_execute_short_circuits_on_empty_checklist(self):
        node = OutputRenderNode()
        out = node.execute({"checklist_items": []})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_s3_gate_accepts_valid_package(self):
        node = OutputRenderNode()
        state = {
            "retrieved_passages": PASSAGES,
            "required_evidence_categories": ["notice_period"],
            "checklist_items": [VALID_CLAIM],
            "customer_notice_evidence_summary_segments": [],
        }
        out = node._extra_security_gate_output(state)
        assert out is state  # unchanged — no rejection

    def test_s3_gate_rejects_unmapped_passage_id(self):
        node = OutputRenderNode()
        claim = {**VALID_CLAIM, "passage_id": "does-not-exist"}
        out = node._extra_security_gate_output(
            {
                "retrieved_passages": PASSAGES,
                "required_evidence_categories": ["notice_period"],
                "checklist_items": [claim],
                "customer_notice_evidence_summary_segments": [],
            }
        )
        assert out["status"] == AgentStatus.ERROR

    def test_s3_gate_rejects_missing_required_category(self):
        node = OutputRenderNode()
        out = node._extra_security_gate_output(
            {
                "retrieved_passages": PASSAGES,
                "required_evidence_categories": ["notice_period", "effective_date"],
                "checklist_items": [VALID_CLAIM],
                "customer_notice_evidence_summary_segments": [],
            }
        )
        assert out["status"] == AgentStatus.ERROR

    def test_s3_gate_rejects_non_verbatim_unsupported_span(self):
        node = OutputRenderNode()
        claim = {**VALID_CLAIM, "transform_type": "verbatim", "source_span": "not present in passage"}
        out = node._extra_security_gate_output(
            {
                "retrieved_passages": PASSAGES,
                "required_evidence_categories": ["notice_period"],
                "checklist_items": [claim],
                "customer_notice_evidence_summary_segments": [],
            }
        )
        assert out["status"] == AgentStatus.ERROR
