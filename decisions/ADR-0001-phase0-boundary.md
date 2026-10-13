# ADR-0001: Phase 0 must be a small offline-first CLI feasibility study

**Status:** Accepted for handoff, 13 October 2026

**Context:** The SRS specifies a sizeable modular application. Asking a coding agent to implement every MVP requirement immediately risks a broad, unvalidated scaffold. The reference Windows laptop has 16 GB RAM, while the official d1-3B CPU path uses FP32 and may exceed available memory.

**Decision:** Build typed frame/inference interfaces, a local still-image adapter, clearly labelled mock inference, offline tests and an opt-in real d1-3B benchmark first. No web app, persistence, continuous video, live camera adapters, streaming or workplace surveillance in Phase 0. A reproducible hardware infeasibility report is an acceptable outcome. The architecture must not couple future camera adapters to Liquid-specific answer fields.

**Consequences:** Phase 0 does not demonstrate the intended full product, but establishes objective feasibility and stable adapter contracts. Phase 1 design remains revisitable after real CPU measurements. A decision about deployment/runtime and the model's license must precede distribution and workplace use.
