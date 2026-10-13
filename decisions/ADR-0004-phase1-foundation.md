# ADR-0004 — minimal authenticated local observation service

Date: 13 October 2026. Status: proposed for Phase 1 review.

The owner authorised Phase 1 after merging Phase 0. The SRS §15 exit gate requires synthetic
frames to traverse capture, inference, persistence and an API; it does not require a dashboard,
episode logic or remote workers. The tested server CPU runtime remains available from Phase 0.

Use operator-owned versioned JSON config, stdlib SQLite, a FastHTML/Starlette local service,
and a single-operator bearer identity supplied by environment. This closes no final application
licence or multi-user identity decision. The SRS FastAPI selection is a proposed baseline;
FastHTML supplies compatible ASGI routes/JSON responses and a minimal diagnostic HTML route,
following the installed FastHTML minimal-stack skill. No ORM, account UI or SPA is needed.

Frames remain byte-oriented. Source location, source ID and inference-engine selection are
independent. Native results retain their score semantics and provenance; no automatic fallback.
SQLite stores immutable query versions and atomic per-frame answers, but not image pixels.
Capture failure records null frame/capture time, not fictional frames. Duplicate frame identity
is checked against content hash before inference. Source/engine failures remain distinct.

Default execution uses explicit synthetic mocks and does not load/download weights. Optional
live capture is one-shot, requires explicit CLI consent and operator-configured endpoints,
and runs in a killable child. No real camera has been tested. Admission permits one POST,
with no queued frames; overload is visible/audited. The injected inference interface retains
its synchronous soft deadline: hung real engines require later process/remote isolation.

Stop at the Phase 1 gate. Future work: Phase 2 query UI/temporal state/events, workload-specific
accuracy, camera/codec/authentication validation, and separately authorised real inference
isolation/placement. Deployment services, remote inference networking and GPU work remain later.
