# ADR-0002 — Inference execution is independent of source and application placement

**Date:** 13 October 2026  
**Status:** Accepted as architectural constraint; remote transport deferred

## Context

The Phase 0 feasibility target is a CPU-only Windows 11 Dell laptop. The eventual product must also support other AI decision models and separate inference machines, such as the user's `antec` server, regardless of their CPU/GPU hardware. The controlling SRS already states INF-001 (provider-neutral inference), INF-010 (additional engine classes), INF-011 (remote inference workers), OPS-010 (processing across hosts) and NFR-017 (secure distributed transport). The Phase 0 hardware target must not accidentally become a permanent architectural restriction.

## Decision

1. Capture location, application/dashboard location, evidence-storage location, and inference execution location are independent configuration dimensions. No implication that all four share a process, host, GPU or filesystem.
2. The inference caller uses stable, provider-neutral `InferenceRequest`/`InferenceResult` types. The caller must not import provider-specific model classes or assume `.to('cpu')`, CUDA, a local pathname, or direct access to model weights. Only the local d1-3B adapter performs its own Torch loading.
3. Image/frame transfer is an adapter-level concern. Phase 0's `FileImageAdapter` accepts local paths, but the generic request should carry a frame reference and allow bytes or a transport-independent resolver. Remote deployments must not rely on shared filesystem access. If using object references, enforce access checks, expiry and transport security. Do not copy sensitive streams across hosts by default.
4. A configured query or routing rule eventually selects an engine instance based on declared capabilities, permitted data destinations, health and capacity. A camera may support queries with different engines. Never silently substitute an engine with different score semantics. Any fallback must be explicit and auditable and must preserve `UNKNOWN/ERROR` when inference cannot be completed.
5. Remote inference must use authenticated encrypted transport, authorised worker identities, bounded queues, deadlines, cancellation/retry discipline, and protected source/frame provenance. These are future implementation requirements, not Phase 0 work.
6. The Phase 0 implementation must prove backend interchangeability with offline deterministic providers; it must **not** implement remote service/network transport at this stage.

## Example future deployment

- Dell Windows 11: USB/RTSP capture, optional dashboard and state engine.
- `antec`: remotely deployed inference engine (possibly a different model and accelerated or CPU-only hardware).
- Frame: selected/cropped still image transferred through authorised transport to the selected worker; no requirement for the worker to connect directly to the camera.
- Result: typed answer with backend identity, model revision, timestamps and origin returned to the central event/measurement service.

## Non-goals and consequences

This ADR neither claims that d1-3B fits in 16 GB nor requires Phase 0 to implement authentication, endpoints, service discovery, remote workers, dashboard, camera streams or a distributed scheduler. The existing SRS phase labels remain unchanged. It protects a future-compatible boundary while preserving the small initial Codex task.
