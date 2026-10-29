# Phase 5 Windows launcher ownership fix — 29 October 2026

VOP accepted HTTP requests while Windows reported its LISTEN socket with PID 0 and the
owned bound socket as NONE. The launcher required a nonzero LISTEN owner, refused to
send the sign-in key, and eventually printed a misleading startup timeout. CPU settling
after a Windows update was not sufficient to resolve this failure. We did not establish
that the update introduced this socket-reporting behaviour.

`tools/run_dashboard.py` retains the normal listener-owner check. If it cannot verify that
owner, it opens an unauthenticated TCP probe and looks up the server side of that exact
connection (both endpoints, ESTABLISHED state, nonzero PID). Existing canonical script,
Python runtime, Windows-account and port checks must pass before any key is sent. A bound
socket alone is insufficient. No authentication, CSRF, host checks or secret storage changes.

Changed files: launcher, `tests/test_lifecycle.py`, README, CHANGELOG, package version
0.6.4 and this report. No new dependency or database migration.

## Validation

- `.venv\Scripts\python.exe -m pytest tests/test_lifecycle.py tests/test_operator_workflow.py -q`:
  **30 passed** in 8.04 seconds. New cases cover the PID-0 listener, correct accepted
  connection, unrelated PID, wrong peer port, bound-only state and missing owner.
  Existing tests retain cross-account/runtime/installation rejection and key non-disclosure.
- `.venv\Scripts\python.exe tools/restart_smoke.py`: **PASS**; GUI and launcher replace
  their synthetic instance, retain 3 observations and the access key. No cameras or model.
- Live read-only comparison on this laptop: original listener check **False**, corrected
  check **True**; authenticated JSON health **ready**. The normal launcher sign-in function
  successfully requested the browser opening; no key or single-use URL was logged.
- The owner confirmed **Observe page is working** after that launch.

The initially stopped service was started under the same Windows account with saved setup.
A diagnostic instance was shut down through the authenticated lifecycle endpoint, then a
normal launcher instance was started. Existing authorized monitoring resumed. Protected
values and imagery were not inspected. No manual camera/model, Tapo, sound, email/SMS or
benchmark test was performed. No new model revision or measurements are claimed.

Full Windows/Ubuntu CI outcomes will be recorded on the pull request. Ownership remains
fail-closed when Windows supplies no attributable accepted connection. The startup retry
window and existing full-history replay cost are unchanged. Remain in Phase 5; recommend
normal Start VOP use and continued owner acceptance. Phase 6 is not started; no auto-merge.
