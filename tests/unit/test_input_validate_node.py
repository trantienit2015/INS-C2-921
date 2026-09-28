from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.input_validate_node import InputValidateNode


class TestInputValidateNode:
    def test_success_sets_validated_input(self):
        node = InputValidateNode()
        out = node.execute({"user_input": '{"cancellation_type": "standard_cancellation"}'})
        assert out["status"] == AgentStatus.SUCCESS
        assert "standard_cancellation" in out["validated_input"]

    def test_empty_input_returns_error(self):
        node = InputValidateNode()
        out = node.execute({"user_input": ""})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_credential_pattern_returns_error(self):
        node = InputValidateNode()
        out = node.execute({"user_input": 'Bearer sometoken123456 "api_key": "x"'})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_non_json_input_falls_back_to_raw_request(self):
        node = InputValidateNode()
        out = node.execute({"user_input": "please cancel my policy"})
        assert out["status"] == AgentStatus.SUCCESS
        assert "raw_request" in out["validated_input"]

    def test_trust_gate_denies_anonymous(self):
        node = InputValidateNode()
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": "{}"})
        assert str(out.get("status")).lower().endswith("error")
        assert any("trust gate" in e.lower() for e in out.get("error_log", []))

    def test_trust_gate_allows_verified_external(self):
        node = InputValidateNode()
        out = node({"caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value, "user_input": "{}"})
        assert out["status"] == AgentStatus.SUCCESS.value
