"""AgentCore Platform v1.0"""

# Deterministic escalation-directory lookup helper (RouteRender step). Pure logic, no side effects, no agenticstar imports — used by
# RouteRenderNode, not registered as a graph node.
#
# Note: the design sketch placed this at `shared/tools/escalation_directory.py`.
# `shared/` is the vendored framework package (imported, never authored by a
# template); the equivalent domain helper for THIS template lives under
# `src/services/` instead — same deterministic-lookup behavior, correct
# ownership boundary. See docs/02_design.md.

from __future__ import annotations

from typing import Any

# Config-provided directory: {cancellation_type: {"queue": ..., "escalation_contact": ...}}
_DEFAULT_ROUTE = {"queue": "insurance-ops-general", "escalation_contact": "ops-escalation@insurer.example"}


def resolve_route(cancellation_type: str, directory: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    """Resolve the human-review queue + escalation contact for a cancellation type.

    Deterministic dict lookup — never calls an LLM or external service.
    Falls back to `_DEFAULT_ROUTE` when the directory is absent or has no entry.
    """
    directory = directory or {}
    route = directory.get(cancellation_type) or _DEFAULT_ROUTE
    return {
        "queue": route.get("queue", _DEFAULT_ROUTE["queue"]),
        "escalation_contact": route.get("escalation_contact", _DEFAULT_ROUTE["escalation_contact"]),
    }
