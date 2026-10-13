# Phase 1 — foundation implementation contract

Authorisation: product owner, 13 October 2026, after merging Phase 0 PR #1.
Basis: SRS v0.2 §15 Phase 1: configuration, source adapters, basic auth, DB schema,
local service and model interface. Exit gate: synthetic capture → inference → persisted
observation → authenticated API. This document records implementation scope; it does not
replace the SRS or expand Phase 1 into the full MVP.

## Deliverables and acceptance

| ID | Acceptance evidence |
|---|---|
| P1-01 | Versioned, validated JSON configuration; synthetic/file sources and independent engine selection; secret values absent from config/API/logs. |
| P1-02 | Synthetic and JPEG/PNG frame acquisition reuse Phase 0 contracts; optional one-shot USB/RTSP/HTTP snapshot adapters; explicit live-source consent and bounded capture. |
| P1-03 | SQLite schema/version migration, immutable question versions, frame provenance, observations and safe configuration persistence; clean restart preserves data. |
| P1-04 | Multiple configured questions over one frame; provider-neutral engine injection/interchangeability; native fields, scores and UTC times retained. |
| P1-05 | Loopback-only HTTP service with mandatory bearer-token authentication for all routes, constant-time secret comparison and denied-access audit; no default secret. |
| P1-06 | Authenticated source listing, explicit one-shot capture, image-byte ingestion and paginated observation retrieval; API never accepts arbitrary source paths/URLs. |
| P1-07 | Capture/inference failures stored as error/unknown with null values; duplicate frame IDs do not rerun inference; bounded concurrency and typed overload/timeout outcomes. |
| P1-08 | Offline pipeline/API/restart/auth/config/failure/adapter tests on Windows and Linux; pinned runtime dependencies and reproducible PowerShell instructions. |

## Chosen boundary

Phase 1 is a single local service with one operator identity (bearer secret supplied by environment),
not the full account/role UI. File configuration is operator-controlled; the API cannot register
arbitrary network destinations. Live capture is one-shot and requires a CLI opt-in; tests use
fakes and synthetic media, never connect to a camera. Capture and model adapters remain separate.
No scheduler, continuous surveillance, dashboard, episode/state engine, event metrics, alerts,
remote inference networking, installer or production deployment is implemented. These remain
later phases. A minimal authenticated HTML service landing page is diagnostic only.

The existing optional real-model benchmark and CPU adapter remain available. Default service
and CI use clearly labelled mock inference, never download/load real weights. Real engine
instances can be supplied through the same Python interface. Real unattended model process
isolation/remote placement needs a later implementation; no silent engine fallback.

FastHTML/Starlette implements the small API and diagnostic HTML route; the SRS FastAPI choice
in §12 is a proposed baseline. SQLite uses the standard library, without an ORM. No application
licence selection is made. Stop after Phase 1 and prepare an unmerged PR for review.
