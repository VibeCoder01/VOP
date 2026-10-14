# Specification change log

## Phase 4 browser error follow-up — 14 October 2026

- Fixed protected camera forms reopening with a hardcoded example endpoint. Saved camera
  selection, address, username and model now reload, with separate edit/add links and blank
  password fields. Added two-camera save/reopen/restart regression coverage.

- Browser capture/setup errors now render readable guidance while API clients retain their
  JSON errors and HTTP status codes. Added a regression check for an occupied capture slot.

## Phase 4 GPU worker and live-camera integration — 13 October 2026

- Added an authenticated loopback worker with process-isolated hard deadlines, bounded admission,
  request identities/cache, explicit remote consent and validated source/model/query provenance.
- Added native backend selection/health and protected Tapo C200/C210/C510W credential setup,
  local one-shot connection tests and registration of the requested human-presence query.
- Added Windows DPAPI and Linux OS Secret Service references; no camera credentials in SQLite,
  exported configuration, worker requests or native diagnostics.
- Verified real pinned d1-3B on antec RTX 5060 Ti in BF16, and a laptop-to-antec GPU request through
  SSH plus application auth. Existing llama service restored after authorised test windows.
- Preserved CPU FP32 configuration and offline mocks; no unverified AMD/Vulkan/GPU pooling path
  or automatic fallback. Actual camera/accuracy gates depend on local owner provisioning.

## Phase 3 reliable development release — 13 October 2026

- Added immutable alert rule revisions, duration/count/health transitions, stable keys, durable
  dashboard delivery, audited acknowledgement/resolution/notes and explicit bounded HTTPS webhook retries.
- Added filtered CSV/JSON exports with provenance and formula protection; validated configuration
  import/export, SQLite-consistent backup/restore and schema-v3 migration with rollback backup.
- Added preview/apply evidence/raw-detail/audit retention, hourly opted-in policy enforcement,
  login throttling and release security/restart/recovery tests.
- Added an allow-listed wheel/ZIP Windows development installer and fresh-install smoke/runbook.
  No new camera/model/GPU test, remote inference, email delivery or licence selection is claimed.

## Phase 2 browser capability — 13 October 2026

- Added browser sessions/CSRF, operator/viewer permissions, immutable question/policy editing,
  source controls, replayed temporal states/episodes, calendar/coverage metrics and SVG trends.
- Added privacy-before-ROI preprocessing, opt-in evidence viewing/deletion, explicit bounded
  background sampling, stale/disconnect handling, schema-v2 migration/backup and browser UI.
- Preserved byte-oriented engine interchangeability and the Phase 0 model pin. No dashboard
  inference pretends to be real vision: default answers remain clearly labelled deterministic mocks.
- Authorised real USB acquisition/software checks passed without retaining pixels. No new
  real-model/GPU/RTSP test, network worker service, application licence or Phase 3 features added.

## Phase 1 foundation — 13 October 2026

- Recorded owner authorisation after Phase 0 PR #1 merge; added a Phase 1 exit contract
  traceable to the existing SRS §15 without renumbering/redesigning requirements.
- Added validated JSON configuration, explicit one-shot source adapters, mandatory
  loopback service authentication, SQLite immutable question versions/observations/audit,
  byte ingestion/idempotency, bounded admission and offline API/persistence tests.
- Reused provider-neutral inference and image validation; added a typed guard for untyped
  provider results. No dashboard, episode metrics, remote workers or Phase 2 features added.

## Phase 0 implementation — 13 October 2026

- Implemented the P0-01–P0-10 contract as a still-image CLI, byte-oriented typed contracts,
  interchangeable synthetic mock engines and an optional pinned Liquid adapter.
- Added offline tests, Windows/Linux CI, locked offline dependencies, synthetic fixture,
  guarded isolated benchmark, PowerShell runbook and feasibility/validation reports.
- Corrected the illustrative plugin starter's SRS reference from v0.1 to v0.2; no SRS
  requirements, IDs or intended plugin semantics changed.
- Application licence remains open. No Phase 1 services or remote worker networking added.

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
