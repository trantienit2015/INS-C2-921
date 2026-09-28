import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.checklist_draft_node import ChecklistDraftNode

PASSAGES = [{"passage_id": "p1", "procedure_version": "v1", "text": "Cancellation takes effect 30 days after notice."}]


class FakeLLM:
    """Canonical BaseLLM.complete() contract: messages: list -> {"content": str, ...}."""

    def __init__(self, response: str):
        self._response = response

    def complete(self, messages: list) -> dict:
        assert isinstance(messages, list), "complete() must receive a messages list, not a bare string"
        return {"content": self._response, "tool_calls": [], "model": "fake-llm"}


VALID_RESPONSE = json.dumps(
    {
        "checklist_items": [
            {
                "item_id": "i1",
                "required_category": "notice_period",
                "claim_id": "c1",
                "artifact_segment_id": "s1",
                "claim_text": "30 day notice period",
                "passage_id": "p1",
                "procedure_version": "v1",
                "source_span": "Cancellation takes effect 30 days after notice.",
                "transform_type": "verbatim",
            }
        ],
        "customer_notice_evidence_summary_segments": [],
    }
)


class TestChecklistDraftNode:
    def test_success_returns_checklist_items(self):
        node = ChecklistDraftNode(llm=FakeLLM(VALID_RESPONSE))
        out = node.execute({"retrieved_passages": PASSAGES})
        assert out["status"] == AgentStatus.SUCCESS
        assert out["checklist_items"][0]["passage_id"] == "p1"
        assert "required_evidence_categories" in out

    def test_empty_passages_returns_error(self):
        node = ChecklistDraftNode(llm=FakeLLM(VALID_RESPONSE))
        out = node.execute({"retrieved_passages": []})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_invalid_llm_response_returns_error(self):
        node = ChecklistDraftNode(llm=FakeLLM("not json"))
        out = node.execute({"retrieved_passages": PASSAGES})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_empty_checklist_items_returns_error(self):
        node = ChecklistDraftNode(llm=FakeLLM(json.dumps({"checklist_items": [], "customer_notice_evidence_summary_segments": []})))
        out = node.execute({"retrieved_passages": PASSAGES})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_no_llm_provisioned_uses_deterministic_fallback(self):
        # Stage 5 deploy-ability: src/api/server.py builds
        # Graph() without an llm — this must succeed via the deterministic
        # stand-in, not crash on None.complete().
        node = ChecklistDraftNode(llm=None)
        out = node.execute({"retrieved_passages": PASSAGES})
        assert out["status"] == AgentStatus.SUCCESS
        assert out["checklist_items"]
        assert all(item["passage_id"] == "p1" for item in out["checklist_items"])
        # transform_type verbatim => source_span must be a real substring of the passage text
        assert all(item["source_span"] in PASSAGES[0]["text"] for item in out["checklist_items"])
