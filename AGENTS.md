# Repository instructions for Codex

The version-controlled source of truth is `SRS-v0.2.md`. The immediate task is **Phase 0 only**, as specified in `CODEX_PHASE_0.md`. The SRS MVP requirements describe later releases; do not implement them all in Phase 0.

## Working rules

- Read `CODEX_PHASE_0.md` and the relevant SRS subsections before implementing Phase 0. Keep changes minimal and traceable to its acceptance IDs.
- Preserve separation between input acquisition, decision/inference, temporal measurement, and UI. In Phase 0, implement only the minimum typed frame/inference interfaces and a CLI proof of concept.
- **Deployment neutrality is mandatory from Phase 0.** The Dell CPU is a benchmark target, **not** the required location of all future models. Preserve an inference request/response interface that could be implemented by a local CPU model, a local GPU model, or an authenticated remote worker (for example on `antec`). The caller must not need to know the hardware, import the model implementation, or require a common filesystem. Do not implement remote transport yet.
- Keep source location independent of inference location: a camera can be captured on one machine and evaluated by another. Model/backend selection must not be conflated with camera/source IDs. Do not assume providers return comparable confidence scores or that fallback to another model is automatically safe.

- **Never fabricate a model result, benchmark, successful camera connection, passing test or deployment.** Label synthetic/mock results clearly. If the real model fails to run, record an honest feasibility outcome and leave the mock-based test suite working.
- Run offline automated tests without model weights, external cameras, CUDA or secrets. Real d1-3B tests are **manual and opt-in**, never part of default CI.
- Do not download models or connect to network cameras without an explicit user action. Do not commit camera credentials, patient/staff imagery, model weights, access tokens or private URLs.
- Prefer pinned, reproducible dependencies and revisions after verified installation. `trust_remote_code=True` may be used only for the explicitly approved LiquidAI model revision, not arbitrary model IDs.
- Do not add React, accounts, SQLite, live dashboards, continuous surveillance, deploy scripts or alerting infrastructure in Phase 0 unless the phase contract explicitly calls for them. Do not change the SRS requirement IDs casually.
- Tests and commands must work on Windows 11 / PowerShell. A Linux CI runner may execute the offline mock tests, but Linux success is not proof of Windows model feasibility.
- Keep network endpoints bound to loopback by default if any temporary diagnostic server is created; prefer CLI-only in Phase 0.
- For each change: implement, test, update the README/runbook, and record any unresolved limitations. Create a conventional git commit only if repository access and the user's workflow permit it. Never claim CI passed without seeing the actual result.

## Required completion report

Provide: changed files; exact commands run and pass/fail results; any commands you could not run; model checkpoint SHA and dependency versions if a real run occurred; measured peak memory/latency **or** the reason these could not be measured; open issues; and a clear `GO / CONDITIONAL GO / NO-GO` recommendation for Phase 1. Do not progress to Phase 1 without an explicit new request.
