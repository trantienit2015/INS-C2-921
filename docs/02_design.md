# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `InsC2921CancellationNoticeEvidenceDraftAgent` (`src/graph/graph.py`)
- **L1 Base**: AgentBaseGraph (outer) — Cat 2, `main` slot = `CancellationEvidenceGraphNode` wrapping
  the inner `CancellationEvidenceWorkflowGraph` (`BaseGraph`, `src/graph/domain_workflow_graph.py`)
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible); all agent-specific
    fields wrapped `NotRequired[...]`
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution; outer does not override `add_edges()`)

## Architecture Overview

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process (`InputValidateNode`) | S-1 trust gate + S-2 credential/PII scan; parse+JSON-serialize the sanitized request metadata | `user_input` | `validated_input` | FunctionNode |
| main (`CancellationEvidenceGraphNode`) | Dispatch to inner subgraph: hybrid retrieval → grounded checklist drafting → route resolution | `validated_input` | `retrieved_passages`, `required_evidence_categories`, `checklist_items`, `customer_notice_evidence_summary_segments`, `human_review_route`, `status` | GraphNode wrapping `CancellationEvidenceWorkflowGraph` |
| ↳ inner `procedure_retrieve` (`ProcedureRetrieveNode`) | Hybrid (dense + metadata-key) retrieval over the versioned procedure/policy-terms KB | inner `user_input` (JSON) | `retrieved_passages` | FunctionNode (inner) |
| ↳ inner `checklist_draft` (`ChecklistDraftNode`) | Low-temperature grounded generation of cited checklist items + summary segments | `retrieved_passages` | `checklist_items`, `customer_notice_evidence_summary_segments`, `required_evidence_categories` | FunctionNode (inner) |
| ↳ inner `route_render` (`RouteRenderNode`) | Deterministic escalation-directory lookup | inner `user_input` (JSON) | `human_review_route` | FunctionNode (inner) |
| post_process (`OutputRenderNode`) | Assemble `formatted_output`; host the S-3 citation-preservation gate | `checklist_items`, `customer_notice_evidence_summary_segments`, `human_review_route`, `retrieved_passages`, `required_evidence_categories` | `formatted_output` | FunctionNode |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process (InputValidate) → main (CancellationEvidenceGraphNode)
  → {inner: procedure_retrieve → checklist_draft → route_render}
  → post_process (OutputRender, S-3 preservation gate) → finalize → END
                                            ↓ (retry)
                                          pre_process
```

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `retrieved_passages` | `NotRequired[list[dict]]` | Ranked procedure/policy passages with `passage_id`/`procedure_version`/`text` | No (set by inner `procedure_retrieve`) |
| `required_evidence_categories` | `NotRequired[list[str]]` | Fixed manifest for the cancellation-notice type | No (set by inner `checklist_draft`) |
| `checklist_items` | `NotRequired[list[dict]]` | Cited evidence-claim checklist items | No (set by inner `checklist_draft`) |
| `customer_notice_evidence_summary_segments` | `NotRequired[list[dict]]` | Cited customer-notice evidence summary segments | No (set by inner `checklist_draft`) |
| `human_review_route` | `NotRequired[dict]` | `{queue, escalation_contact}` | No (set by inner `route_render`) |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, caller_trust_level)
- [x] ConnectionPolicy (retry/timeout strategy — `agent.yaml config.max_retry`/`timeout_seconds`)
- [ ] SecurityViolationError — not used directly; S-2/S-1 rejection is expressed as a fail-closed
      `AgentStatus.ERROR` return from `execute()`, per the non-raising validation pattern
- [x] S-2: `_extra_security_gate_input()` — not overridden; the deterministic credential/PII scan
      (My Number, policy-ID, Bearer/JWT, credential-JSON) runs directly inside
      `InputValidateNode.execute()` (fail-closed `ERROR`, no raise)
- [x] S-3: `_extra_security_gate_output()` — implemented on `OutputRenderNode` (preservation
      variant, fail-safe): verifies every `checklist_items[]`/`customer_notice_evidence_summary_segments[]`
      entry's `claim_id`/`passage_id`/`procedure_version`/`source_span`/`transform_type` against
      `retrieved_passages`, and confirms every `required_evidence_categories` entry has ≥1 valid
      claim. Rejects the whole package (`status = ERROR`) on any violation — never drops an item.
- [x] S-4: `emit_trace_event()` — ≥1 domain event per node (`cancellation_request_validated`,
      `cancellation_evidence_dispatched`/`cancellation_evidence_completed` on the GraphNode wrapper,
      `procedure_passages_retrieved`, `checklist_drafted`, `human_review_route_resolved`,
      `cancellation_evidence_package_rendered`)

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — Cat 2, outer `AgentBaseGraph` + `main` slot `GraphNode`
  wrapping inner `BaseGraph` (`CancellationEvidenceWorkflowGraph`)
- **Composition target**: `src/graph/domain_workflow_graph.py::CancellationEvidenceWorkflowGraph`
- **Error propagation strategy**: propagate (`error_strategy = "propagate"` — fail fast; no HITL,
  `propagate_hitl = False`)

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Fixed multi-step pipeline (Cat 2), not an autonomous think-act-observe loop |
| Composition pattern | Flat 3-slot (Cat 1 style) | GraphNode + inner BaseGraph | GraphNode + inner BaseGraph | Cat 2 gate-composition requires the 3-layer outer/GraphNode/inner pattern, not a flat MainNode ohm multiple steps |
| Escalation-directory helper location | `shared/tools/` (proposal sketch) | `src/services/escalation_directory.py` | `src/services/` | `shared/` is the vendored framework package (import-only); a template cannot author new modules into it — the equivalent domain helper lives under `src/services/` instead |

## Deviations from the initial design sketch (documented, non-blocking)

- The initial design sketch placed the escalation-directory helper at
  `shared/tools/escalation_directory.py`. Since `shared/` is the vendored L1 framework package
  (import-only boundary — import isolation), the equivalent deterministic
  lookup lives at `src/services/escalation_directory.py` instead. Behavior and ownership
  (deterministic dict lookup, no side effects, not a graph node) are unchanged.
- `procedure_version` is a config-level selector (`agent.yaml`/`GraphNode._parent_config()`), not a
  State field — it flows to the inner `ProcedureRetrievalService` via constructor injection rather
  than through State, per the "config to inner via `_parent_config()`, not State" Cat 2 rule.
- The real vector-store connector and production LLM client are customer/deploy-time dependencies
  — this implementation depends only on
  the narrow `VectorStoreClient.hybrid_search(...)` / `llm.complete(...)` interfaces so the pipeline
  is fully unit/integration-testable with fakes before the real corpus/LLM wiring lands.
