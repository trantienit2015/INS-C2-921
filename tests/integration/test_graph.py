import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph

PASSAGES = [
    {"passage_id": "p1", "procedure_version": "v1", "text": "Cancellation takes effect 30 days after notice."},
    {"passage_id": "p2", "procedure_version": "v1", "text": "A processing fee of 2000 JPY applies for early cancellation."},
    {"passage_id": "p3", "procedure_version": "v1", "text": "Cancellation must be acknowledged by signed form."},
]

VALID_LLM_RESPONSE = json.dumps(
    {
        "checklist_items": [
            {
                "item_id": "i1",
                "required_category": "effective_date",
                "claim_id": "c1",
                "artifact_segment_id": "s1",
                "claim_text": "30 day effective date",
                "passage_id": "p1",
                "procedure_version": "v1",
                "source_span": "Cancellation takes effect 30 days after notice.",
                "transform_type": "verbatim",
            },
            {
                "item_id": "i2",
                "required_category": "notice_period",
                "claim_id": "c2",
                "artifact_segment_id": "s2",
                "claim_text": "notice period",
                "passage_id": "p1",
                "procedure_version": "v1",
                "source_span": "Cancellation takes effect 30 days after notice.",
                "transform_type": "verbatim",
            },
            {
                "item_id": "i3",
                "required_category": "fee_or_refund_disclosure",
                "claim_id": "c3",
                "artifact_segment_id": "s3",
                "claim_text": "fee disclosure",
                "passage_id": "p2",
                "procedure_version": "v1",
                "source_span": "A processing fee of 2000 JPY applies for early cancellation.",
                "transform_type": "verbatim",
            },
            {
                "item_id": "i4",
                "required_category": "acknowledgment_method",
                "claim_id": "c4",
                "artifact_segment_id": "s4",
                "claim_text": "acknowledgment method",
                "passage_id": "p3",
                "procedure_version": "v1",
                "source_span": "Cancellation must be acknowledged by signed form.",
                "transform_type": "verbatim",
            },
        ],
        "customer_notice_evidence_summary_segments": [],
    }
)


class FakeVectorStore:
    def hybrid_search(self, query, top_k, procedure_version, metadata_filter=None):
        return PASSAGES[:top_k]


class FakeLLM:
    """Canonical BaseLLM.complete() contract: messages: list -> {"content": str, ...}."""

    def complete(self, messages: list) -> dict:
        assert isinstance(messages, list), "complete() must receive a messages list, not a bare string"
        return {"content": VALID_LLM_RESPONSE, "tool_calls": [], "model": "fake-llm"}


def _build_agent():
    agent = Graph(config={
        "vector_store": FakeVectorStore(),
        "llm": FakeLLM(),
        "procedure_version": "v1",
        "top_k": 6,
        "escalation_directory": {},
        "max_retry": 1,
    })
    agent.compile()
    return agent


class TestGraph:
    def test_full_pipeline_success(self):
        agent = _build_agent()
        ctx = InvocationContext(session_id="it-1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="tester")
        result = agent.invoke(json.dumps({"cancellation_type": "standard_cancellation"}), ctx=ctx)
        assert result["status"] == AgentStatus.SUCCESS.value
        # AgentBaseGraph.get_output() shapes the top-level invoke() response as
        # {"output": formatted_output or result, ...} — not a raw "formatted_output" key.
        assert result["output"]["checklist_items"]
        assert result["output"]["human_review_route"]["queue"] == "insurance-ops-general"

    def test_empty_input_fails_closed(self):
        agent = _build_agent()
        ctx = InvocationContext(session_id="it-2", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="tester")
        result = agent.invoke("", ctx=ctx)
        assert str(result["status"]).lower().endswith("error") or str(result["status"]).lower().endswith("cancelled")

    def test_insufficient_trust_denied(self):
        agent = _build_agent()
        ctx = InvocationContext(session_id="it-3", caller_trust_level=TrustLevel.ANONYMOUS, caller_id="tester")
        result = agent.invoke(json.dumps({"cancellation_type": "standard_cancellation"}), ctx=ctx)
        assert str(result["status"]).lower().endswith("error")
