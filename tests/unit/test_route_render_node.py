import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.route_render_node import RouteRenderNode

DUMMY_CHECKLIST = [{"item_id": "i1", "claim_id": "c1"}]


class TestRouteRenderNode:
    def test_success_resolves_configured_route(self):
        directory = {"standard_cancellation": {"queue": "insurance-ops-cancellations", "escalation_contact": "cancel-team@insurer.example"}}
        node = RouteRenderNode(escalation_directory=directory)
        out = node.execute({
            "user_input": json.dumps({"cancellation_type": "standard_cancellation"}),
            "checklist_items": DUMMY_CHECKLIST,
        })
        assert out["status"] == AgentStatus.SUCCESS
        assert out["human_review_route"]["queue"] == "insurance-ops-cancellations"

    def test_unknown_cancellation_type_falls_back_to_default(self):
        node = RouteRenderNode(escalation_directory={})
        out = node.execute({
            "user_input": json.dumps({"cancellation_type": "unmapped_type"}),
            "checklist_items": DUMMY_CHECKLIST,
        })
        assert out["status"] == AgentStatus.SUCCESS
        assert out["human_review_route"]["queue"] == "insurance-ops-general"

    def test_invalid_input_still_succeeds_with_default_route(self):
        node = RouteRenderNode()
        out = node.execute({"user_input": "not json", "checklist_items": DUMMY_CHECKLIST})
        assert out["status"] == AgentStatus.SUCCESS
        assert out["human_review_route"]["queue"] == "insurance-ops-general"

    def test_upstream_error_short_circuits(self):
        node = RouteRenderNode()
        out = node.execute({"user_input": json.dumps({"cancellation_type": "x"}), "status": AgentStatus.ERROR})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_no_checklist_items_short_circuits(self):
        node = RouteRenderNode()
        out = node.execute({"user_input": json.dumps({"cancellation_type": "x"}), "checklist_items": []})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]
