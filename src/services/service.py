"""AgentCore Platform v1.0"""

# Service layer: domain queries, external API wrappers, data aggregation.
# Must NOT contain business logic, routing, or credentials.
# Nodes call this; this calls shared/services/ for external integrations.

from __future__ import annotations

import re
from typing import Any, Protocol

# S-2 domain-specific deterministic patterns:
# 個人番号 (My Number, 12 digits), policy-identifier format, Bearer/JWT token, credential-shaped JSON.
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{10,}\b", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9._-]{10,}"),  # JWT header prefix
    re.compile(r'"(?:api[_-]?key|password|secret|token)"\s*:', re.IGNORECASE),
    re.compile(r"\b\d{12}\b"),  # 個人番号 (My Number, 12-digit individual number)
    re.compile(r"\bPOL-\d{6,}\b", re.IGNORECASE),  # internal policy-identifier format
)


def has_credential_leak(text: str) -> bool:
    """Deterministic scan for regulated-identifier / credential-shaped content."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS)


class VectorStoreClient(Protocol):
    """Injected vector-store connector — hybrid dense + metadata-key retrieval.

    Real implementation is wired via framework/shared services at deploy time
    (`framework/`/`shared/` connector). Node-level code only depends on this narrow interface so
    unit tests can inject a fake.
    """

    def hybrid_search(
        self, query: str, top_k: int, procedure_version: str, metadata_filter: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...


class ProcedureRetrievalService:
    """Hybrid retrieval over the versioned internal procedures + policy-terms KB."""

    def __init__(self, vector_store: VectorStoreClient, procedure_version: str, top_k: int = 6):
        self._vector_store = vector_store
        self._procedure_version = procedure_version
        self._top_k = top_k

    @property
    def vector_store(self) -> VectorStoreClient | None:
        """Public read of the injected connector — lets the node check `is None`
        (Stage ⑤ deploy-ability: entry-point may not provision this dep yet)."""
        return self._vector_store

    @property
    def procedure_version(self) -> str:
        return self._procedure_version

    def retrieve(self, query: str, cancellation_type: str | None = None) -> list[dict[str, Any]]:
        """Retrieve ranked procedure/policy passages for the given query.

        `procedure_version` is an explicit config selector so the current
        edition is retrieved.
        """
        metadata_filter = {"cancellation_type": cancellation_type} if cancellation_type else None
        return self._vector_store.hybrid_search(
            query=query,
            top_k=self._top_k,
            procedure_version=self._procedure_version,
            metadata_filter=metadata_filter,
        )
