# View and Configure modes — 20 October 2026

Changed `src/vop/browser_auth.py`, `src/vop/dashboard.py`, `tests/test_ui_modes.py`,
existing browser login helpers in `tests/test_phase2_browser_storage.py`,
`tests/test_phase3_release.py`, `tests/test_phase4_worker.py`, `tests/test_removal.py`,
`tools/phase2_smoke.py`, `tools/phase3_smoke.py`, `tools/phase4_smoke.py`, README,
CHANGELOG and this report. This is a UI refinement within the authorised Phase 4 pilot,
supporting the existing UI and operator/viewer requirements, not a new phase.

Fresh manual or launcher sign-in defaults to View mode. A signed browser session remembers
an explicit Configure selection until switched back or signed in again. The sidebar shows
the current mode and a native CSRF-protected switch; no new credentials or accounts.
View navigation contains Observe, Individual Observations, Continuous Observations
(Episodes) and Trends. Configure adds cameras, engines, questions and settings, monitoring,
image-saving, deletion and restart controls. Operators can still observe enabled inputs
and read permitted saved images in View mode. Viewer credentials retain their restrictions
and cannot enter Configure. Mode changes do not update source controls or worker sessions.

Browser middleware gates direct setup links and configuration/deletion/lifecycle writes.
A setup GET redirects to a page with a mode-switch button; a stale browser form redirects to the same page with a no-changes-saved notice. JSON clients
receive HTTP 403 with `configure_mode_required` and `/configure` remediation. Reads of observation results,
evidence and JSON API metadata remain available subject to existing role checks. Bearer
API clients retain existing permissions. Duplicate view query parameters use the same
parsing as the dashboard. Switching modes does not wait for the capture admission slot.

Windows validation commands and actual results:

- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_modes.py -q`: 3 passed in 2.29 s
  after the final duplicate-query and stale-form remediation regressions were added. Covers default/fresh/launcher login,
  CSRF, mode persistence, configuration navigation and direct routes, denied writes,
  unchanged source controls, saved-image access, hidden deletion, explicit mock capture,
  viewer denial and bearer compatibility.
- `.\.venv\Scripts\python.exe -m pytest tests/test_removal.py tests/test_phase3_release.py -q --disable-warnings`:
  25 passed in 13.39 s after older setup tests explicitly selected Configure mode.
- `.\.venv\Scripts\python.exe -m pytest -q`: 308 passed, 4 skipped in 105.89 s.
  The skips are Linux-only helper tests on Windows. Subsequent small guard/admission changes
  were checked with the focused mode/lifecycle tests: 10 passed in 6.12 s, then the final
  three mode regressions above. Initial failures were older tests assuming configuration
  access immediately after login; their helpers now select Configure explicitly.
- `.\.venv\Scripts\python.exe tools/phase2_smoke.py`: PASS; real loopback synthetic browser
  session, six views, CSRF forms, replay, image restrictions/deletion and 21 answers after restart.
- `.\.venv\Scripts\python.exe tools/phase3_smoke.py`: PASS; synthetic/mock rules, acknowledgement,
  exports, retention preview and 18 restored observations.
- `.\.venv\Scripts\python.exe tools/phase4_smoke.py`: PASS; explicit mock worker over actual
  loopback HTTP, health form, 3 answers after restart and actual Windows DPAPI.
- `git diff --check`: passed.

The real laptop dashboard's JSON health endpoint refused connection: no server was running,
so no live restart or deployment is claimed. Open Start VOP to load this code. Existing
running monitoring is not stopped by a mode switch. No live camera, Antec, GPU or real-model
tests were run for this interface change; smoke captures and inference were explicitly
synthetic/mock. No dependencies, database schema or model versions changed. Historical
approved d1 revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Limitations: modes separate interface tasks; they are not a new authentication boundary or
separate accounts. An authorised operator can switch without a second key. View is the
default, not strictly read-only: explicit enabled-input observation remains available.
Recommend reviewing both modes in the existing Phase 4 pilot. Phase 5 remains unauthorised.
