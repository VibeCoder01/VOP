# Specification change log

## v0.2.1 — 13 October 2026 — Inference placement clarification

- Confirmed that the SRS already mandates provider-neutral inference (INF-001) and plans remote workers (INF-011, OPS-010, NFR-017). **No SRS requirements or numbering changed.**
- Added a Phase 0 design-only guardrail: CPU-only Dell benchmark is not a local-only product decision. Camera capture, inference, storage and dashboard may reside on different machines in later deployments.
- Required a location-neutral inference contract and offline interchangeability test using two mock provider instances; no remote network service, RPC or hardware requirement added to Phase 0.
- Documented model placement, payload portability, explicit engine routing and safe future fallback behaviour in ADR-0002.

## v0.2 — 13 October 2026 — Final Codex handoff review

- Preserved existing requirement IDs and modular system architecture.
- Added a controlling, executable **Phase 0** scope and acceptance matrix in `CODEX_PHASE_0.md`.
- Added concise repository instructions (`AGENTS.md`) and a ready-to-paste Codex task (`CODEX_START_PROMPT.md`).
- Resolved scope drift: no UI, database, RTSP, live camera or full MVP delivery in Phase 0; offline/mock vertical slice first.
- Required explicit real-model opt-in and accurate recording of memory/latency, model revision, errors and non-execution.
- Clarified that `noul`, `choice` and `score` are provider responses; durations, frequencies, rates and event episodes are later derived measurements, not model-native numeric outputs.
- Added a model/runtime trust and licensing review gate. Liquid's LFM Open License v1.0 is **not** necessarily equivalent to an OSI-approved software licence; evaluate applicable usage and redistribution conditions independently.
- Clarified that CPU feasibility failure is a valid Phase 0 finding, not permission to report success or skip acceptance evidence.
- Added safety note about missing frames, preflight resource checks, local/private test images and offline CI.

## v0.1 — 13 October 2026 — Initial requirements baseline

- Product vision, architectural boundaries, detailed requirements, data model, plugin contracts, acceptance scenarios and roadmap.
