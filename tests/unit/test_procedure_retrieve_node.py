import json

from framework.schemas.agent_status import AgentStatus

from src.nodes.procedure_retrieve_node import ProcedureRetrieveNode
from src.services.service import ProcedureRetrievalService


class FakeVectorStore:
    def __init__(self, passages):
        self._passages = passages

    def hybrid_search(self, query, top_k, procedure_version, metadata_filter=None):
        return self._passages[:top_k]


PASSAGES = [
    {"passage_id": "p1", "procedure_version": "v1", "text": "Cancellation takes effect 30 days after notice."},
    {"passage_id": "p2", "procedure_version": "v1", "text": "A processing fee of 2000 JPY applies."},
]


class TestProcedureRetrieveNode:
    def test_success_returns_retrieved_passages(self):
        service = ProcedureRetrievalService(vector_store=FakeVectorStore(PASSAGES), procedure_version="v1")
        node = ProcedureRetrieveNode(retrieval_service=service)
        payload = json.dumps({"cancellation_type": "standard_cancellation"})
        out = node.execute({"user_input": payload})
        assert out["status"] == AgentStatus.SUCCESS
        assert out["retrieved_passages"] == PASSAGES

    def test_invalid_inner_input_returns_error(self):
        node = ProcedureRetrieveNode(retrieval_service=ProcedureRetrievalService(FakeVectorStore(PASSAGES), "v1"))
        out = node.execute({"user_input": "not json"})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_no_passages_returns_error(self):
        node = ProcedureRetrieveNode(retrieval_service=ProcedureRetrievalService(FakeVectorStore([]), "v1"))
        out = node.execute({"user_input": json.dumps({"cancellation_type": "x"})})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_no_retrieval_service_zero_arg_construct_is_safe(self):
        # PB-6 requires this node to instantiate with no args (default None).
        node = ProcedureRetrieveNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR

    def test_no_vector_store_provisioned_uses_deterministic_fallback(self):
        # Stage 5 deploy-ability: src/api/server.py builds
        # Graph() without a vector_store — this must succeed via the
        # deterministic stand-in, not crash on None.hybrid_search().
        service = ProcedureRetrievalService(vector_store=None, procedure_version="v2")
        node = ProcedureRetrieveNode(retrieval_service=service)
        out = node.execute({"user_input": json.dumps({"cancellation_type": "standard_cancellation"})})
        assert out["status"] == AgentStatus.SUCCESS
        assert out["retrieved_passages"]
        assert out["retrieved_passages"][0]["procedure_version"] == "v2"
