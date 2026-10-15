# Phase 4 camera and engine workspaces — 15 October 2026

The owner requested separate engine and camera creation, configuration, editing and use,
with a restrained interface and simple task instructions. This implements that separation
within Phase 4. It does not claim formal ASD-STE100 certification or Apple design approval.

## Operator workflow

- Observe runs a single observation or the existing monitoring workflow. Actions precede
  statistics and history. Camera capture and inference retain their separate contracts.
- Cameras lists saved cameras. Add camera and Edit camera contain only camera settings.
  Save camera stores protected details; it does not connect, infer or start monitoring.
  A camera detail page provides Test camera, Observe, Questions and observation-policy links.
- Engines lists named profiles. Add engine and Edit engine contain only engine settings.
  Save engine does not select it. Use engine explicitly selects it for all observations.
  Editing a selected profile or replacing its saved key leaves active settings/key unchanged
  until Use engine. The selected profile ID and configuration survive process restart.
  Switching away from an owned session requests its existing stop/restoration path.
- Questions, History, Trends and Settings have distinct navigation destinations. Generic
  file/synthetic inputs remain under Settings → Other inputs. Legacy integration bookmarks
  and POST clients remain supported; the old combined page is now a two-link setup index.

Named engine profiles use release_settings, without a schema/dependency migration. Existing
selected engine/camera configuration is preserved and the current engine is adopted as a saved
profile. Keys remain protected OS values; profiles contain references. New key revisions use
separate references so an edit cannot mutate the active key. No new model/provider is installed.

The visual system uses a light sidebar, neutral surfaces, one blue action colour, semantic
status colours, clear spacing, native forms, visible keyboard focus, responsive rules and
reduced-motion support. Instructions use short sentences and explicit verbs. Technical fields
and provenance remain available in details sections. Saving, testing and using are distinct.

## Changed files

- src/vop/dashboard.py: navigation, shared visual system, action-first Observe, result language
  and links to the relevant camera or engine workspace.
- src/vop/integration_ui.py: camera/engine list, detail and editor routes; saved profile handling,
  explicit selection and legacy route compatibility. Shared selection preserves busy guards.
- src/vop/ui_readiness.py: separate camera/engine remediation targets and simpler camera text.
- src/vop/removal.py: camera lists show only removed camera inputs, preserving restore behavior.
- tests/test_separate_setup.py: independence, save/use, restart, key isolation, auth/CSRF,
  busy operation, generated-name and invalid-address regressions.
- tests/test_operator_workflow.py, test_phase2_browser_storage.py and test_phase4_worker.py:
  updated page/copy/contrast checks while retaining functional acceptance assertions.
- tools/phase2_smoke.py and phase4_smoke.py: new workspace names in existing HTTP checks.
- README.md, CHANGELOG.md and CODEX_PHASE_4_PLAN.md: operating instructions and scope.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 261 passed, 4 skipped (Linux-only helper cases)
.\.venv\Scripts\python.exe tools\phase2_smoke.py
# PASS: browser session, CSRF, episode/replay, evidence denial and process restart; synthetic
.\.venv\Scripts\python.exe tools\phase4_smoke.py
# PASS: actual loopback mock-worker HTTP, disconnect Unknown, restart, real Windows DPAPI
.\.venv\Scripts\python.exe -m pip check
# No broken requirements found
.\.venv\Scripts\python.exe tools\build_release.py
# PASS
git diff --check
```

Final full local suite: 261 passed, 4 skipped in 40.92 seconds. Final release ZIP SHA-256:
`b261903398d239a5895befbdb0e9cc06880396eacaf87780b25e59f6bb6be332`.
After reloading only the idle laptop app, authenticated JSON health returned HTTP 200 with
automatic recovery enabled, C200 protected setup ready and liquid-d1-3b still selected. A
metadata check confirmed the adopted saved engine profile matches the prior active profile.

A separate disposable fixture on loopback port 8879 contained only generated camera details
and synthetic data. Playwright opened it, signed in and navigated Observe → Cameras → Engines.
Observe and Cameras desktop screenshots were inspected at 1440 × 1000. A subsequent browser
command was rejected by automatic approval review with only "blocked by policy"; it was not
retried. No complete editor/mobile browser acceptance pass is claimed. The synthetic server
was stopped. The live user's pages were not inspected through browser automation.

No real camera capture or GPU/model benchmark was performed. Model weights were not loaded;
historical d1 revision remains 051bcc464b01b9f92942b364d9586b0ef5912432. Automatic Antec recovery,
the timed restoration helper, raw observations and question versions retain their existing
contracts. The earlier post-reboot protected-store discrepancy remains unresolved.

Continue supervised Phase 4 acceptance: open Cameras, review a camera, then Observe; open
Engines, save an edit and verify it applies only after Use engine. Complete editor/mobile and
physical-reboot acceptance separately. Phase 5 remains unauthorised; no auto-merge is requested.
