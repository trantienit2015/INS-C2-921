# INS-C2-921 — Insurance Policy Cancellation Notice Evidence Draft Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: INS

## Overview

Insurance operations staff use this agent after they receive an authorized policy-cancellation
request. It produces a cited evidence checklist for review, never a cancellation, eligibility or
refund decision. The caller sends the request metadata as a JSON string in `input`, for example
`{"cancellation_type": "customer_initiated", "request_id": "REQ-0001"}`. Plain text is accepted
too and is treated as the raw request.

The pipeline:

1. **Input validation** rejects empty input, and input containing a regulated identifier (such as
   a My Number) or a credential-shaped string.
2. **Procedure retrieval** runs a hybrid search for the versioned procedure and policy-term
   passages that match the cancellation type, through a pluggable `vector_store` client.
3. **Checklist drafting** asks an LLM for a checklist and an evidence summary for the customer
   notice. Each item cites a retrieved passage and covers one required evidence category
   (effective date, notice period, fee or refund disclosure, acknowledgment method).
4. **Review routing** picks the human-review queue and escalation contact from a configurable
   escalation directory.
5. **Output rendering** rejects the draft if any required category is missing or an item does
   not cite a retrieved passage.

**Current behaviour without providers.** The repository ships with no vector store and no LLM
configured. In that mode retrieval returns one fixed, clearly marked placeholder passage
(`stub-procedure-001`). Checklist drafting returns one placeholder item per required category
(`stub-item-N`, claim text "Deterministic stub coverage for ..."). The review route falls back to
a generic queue with an `example` contact address. Each fallback emits its own trace event. This
mode shows the pipeline shape and contract only. Its output is not real procedure content. To
use the template for real work, provide a `vector_store`, an `llm` client and an
`escalation_directory` through the graph configuration.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | 3.11 or later |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and test specification
```

See `docs/02_design.md` for the design and `docs/03_test_spec.md` for the test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
