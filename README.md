# Visual Observability Platform — Codex handoff v0.2.1

**Status:** Reviewed requirements and Phase 0 coding brief. This archive contains *specification documents*, not an implemented application.

## Read in this order

1. **`CODEX_START_PROMPT.md`** — paste its body as the first Codex task.
2. **`CODEX_PHASE_0.md`** — controlling acceptance contract for first implementation.
3. **`AGENTS.md`** — concise instructions intended for the repository root (Codex discovers it automatically).
4. **`SRS-v0.2.md`** — authoritative product specification and later-phase requirements. `SRS-v0.2.docx` is the editable review counterpart.
5. `plugin-contracts.yaml` and Mermaid diagrams — illustrative architectural scaffolding, not frozen code or tested schemas.
6. `CHANGELOG.md`, `decisions/ADR-0001-phase0-boundary.md` and `decisions/ADR-0002-inference-placement.md` — review decisions and scope rationale.

## Installation into a new repository

Copy the entire package into a new private repository. Keep `AGENTS.md`, `CODEX_PHASE_0.md` and `CODEX_START_PROMPT.md` in its root (or adjust paths in the task). Do **not** distribute actual camera footage or model weights with the source. Pick the project's own licence separately; do not assume Liquid's model licence covers the application or vice versa.

## Critical boundary

**Phase 0 is not the MVP.** It is a Windows CPU feasibility study and simple provider-neutral CLI proof of concept. It is complete only when offline tests and documentation pass, and the real-model test is recorded honestly as passed, blocked, failed or not-run. Live camera integration, web dashboards, events, rules, authentication and persistence follow later. **Do not interpret the local CPU benchmark as a deployment constraint:** remote and heterogeneous inference are supported by the SRS design, but remote transport is not implemented in Phase 0.

## Contents

- `SRS-v0.2.md` and `SRS-v0.2.docx` — product baseline
- `CODEX_PHASE_0.md` — precise Phase 0 scope, tests and exit criteria
- `AGENTS.md` — repository coding-agent constraints
- `CODEX_START_PROMPT.md` — immediate implementation prompt
- `CHANGELOG.md` and `decisions/*.md` — review trail and explicit local/remote inference design guardrail
- `architecture.mmd`, `data-model.mmd`, `decision-state.mmd` — editable diagrams
- `plugin-contracts.yaml` — preliminary plugin contract starter
- `assets/*.png`, `assets/*.dot` — renderings and graph sources

## Sources

The official model card and licence are listed in §18 of `SRS-v0.2.md`. This package does not reproduce the model weights, its licence file or camera credentials.
