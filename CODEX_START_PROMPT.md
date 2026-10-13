# Ready-to-paste task for Codex

Implement **Phase 0 only** for the Visual Observability Platform.

Treat `SRS-v0.2.md` as the product specification and `CODEX_PHASE_0.md` as the controlling scope and acceptance contract for this task. Follow repository-root `AGENTS.md`.

Start by checking the repository and stating a short implementation plan. Implement the smallest clean Python CLI proof of concept, typed interfaces, deterministic mock inference, synthetic file-image fixture, opt-in LiquidAI/d1-3B CPU adapter and diagnostic benchmark, plus offline tests and Windows 11 setup guidance. Do **not** implement the full MVP, dashboard, database, RTSP, continuous camera streams or service deployment yet.

Hardware target for the later operator-run benchmark: Intel i5-10310U, 16 GB RAM, Windows 11. Never infer that FP32 will fit. Model download and benchmark must be explicitly opt-in. Never fabricate results or claim a CPU benchmark ran if your environment cannot perform it. Keep the default CI path offline and independent of the model. Use the official `system_one` API and preserve native decision fields. Pin dependencies and the model revision once they are verified. **Architecture guardrail:** the CPU-only experiment does not constrain deployment. Preserve a provider-neutral inference boundary so a future worker on `antec` (CPU or GPU, possibly a different AI model) can fulfil the same typed requests as a local engine. Inputs, queries and measurement logic must remain independent of model placement. Do not implement remote networking in Phase 0; demonstrate interchangeability with offline mock providers.

Run all available offline tests, fix their failures, and record exact commands and results. Produce a clear `GO / CONDITIONAL GO / NO-GO` Phase 1 recommendation, using actual measurements or an explicit untested/blocking reason. Stop after Phase 0. Do not begin Phase 1 until I ask.
