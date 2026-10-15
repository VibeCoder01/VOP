# Phase 4 visible removal and deletion — 15 October 2026

The owner requested visible deletion for cameras, engines, observations and related items.
This adds controls and documented retention deletion under OPS-007/NFR-015. It performs no
automatic purge and does not delete anything in the owner's workspace during implementation.

## Available actions

- Cameras: Remove is visible on each list row and in a separate detail-page section. Existing
  recoverable removal stops monitoring and dependent rules. History and protected details stay;
  Removed cameras offers Restore with monitoring/evidence off. Questions retain their existing
  recoverable Remove action.
- Engines: Delete profile opens confirmation. A selected profile cannot be deleted; choose a
  different engine first. The profile is deleted, while protected/shared keys, model files and
  observation provenance remain. No fallback engine is selected automatically.
- Observations: new navigation/list with newest-first paging, input filter, capture deletion
  and full input-history deletion. Result/detail pages also link to Delete capture. Removed
  inputs' recorded history remains accessible here until explicitly deleted.
- Delete capture: preview all answers sharing the capture, its raw result and retained image.
  Confirmed deletion removes them together, deletes related alerts/deliveries, pauses affected
  rules with a new immutable rule revision, and rebuilds related episodes/metrics. Minimal
  timestamp-only gap records replace the deleted positions, with no model answers/images/raw
  payload. They are labelled retention_gap, excluded from answer counts/list/detail/model
  provenance, and included only in temporal replay to avoid false coverage across deletion.
- Delete input history: monitoring must be paused. All captures and deletion-gap records for
  that input are deleted. Camera/engine/question setup and immutable specifications remain.

GET previews never delete. POST requires operator access, CSRF, a matching preview fingerprint
and capture/rule-processing locks. Changed effects must be reviewed again. The deletion and
event rebuild share one SQLite transaction; failures roll back. Memory previews are cleared
and the existing secure-delete setting plus a best-effort WAL checkpoint are used. No forensic
erasure of external copies is promised. Audit records, backups and already-sent messages stay,
as stated in the confirmation. No new permission checkboxes or dependencies were added.

## Changed files

- src/vop/history_deletion.py: effect selection, confirmation, atomic deletion/rebuild and gaps.
- src/vop/storage.py: gap-aware replay, filtered answer access/counts and newest-first paging.
- src/vop/measurements.py: gap markers affect Unknown/coverage but not actual sample counts or
  last-observation IDs. Existing confirmation/gap policies remain in use.
- src/vop/reliable.py: metric export excludes deletion metadata from model provenance.
- src/vop/dashboard.py: Observations pages/navigation and visible data deletion links.
- src/vop/integration_ui.py: camera-list removal, separate removal section and profile deletion.
- src/vop/removal.py: camera-specific confirmation/restore destinations and listing heading.
- src/vop/service.py: install confirmed history-deletion routes.
- tests/test_history_deletion.py: nine offline regressions covering shared data/image deletion,
  restart/replay gaps, source scope, rule/delivery cleanup, auth/CSRF/busy/stale previews,
  transaction rollback, current-engine guard, preserved keys, camera restore and marker counts.
- tests/test_phase2_browser_storage.py: inspect actual asset URLs rather than searching arbitrary
  HTML for "cdn", which could occur randomly inside a CSRF token.
- README.md, CHANGELOG.md and CODEX_PHASE_4_PLAN.md: clear operating semantics and scope.

## Actual validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 272 passed, 4 skipped in 37.50s (Linux-only helper cases)
.\.venv\Scripts\python.exe tools\phase3_smoke.py
# PASS: synthetic alerts, export, retention preview, backup/restart
.\.venv\Scripts\python.exe tools\phase4_smoke.py
# PASS: synthetic loopback worker, disconnect Unknown, restart and real Windows DPAPI
.\.venv\Scripts\python.exe -m pip check
# No broken requirements found
.\.venv\Scripts\python.exe tools\build_release.py
# PASS
git diff --check
```

Release ZIP SHA-256: `a11705401d41815f861ff7216d69e04d8a5689a3bec7796a45b9b81b1d12bf57`.
After reloading only the idle laptop app, authenticated JSON health returned HTTP 200 and C200
protected setup remained readable. Before/after counts for actual observations, runs and frames
were identical. No actual data-deletion route was called against the owner's database.

No real camera capture, model load, GPU benchmark or new browser visual pass was performed.
Historical d1 revision remains 051bcc464b01b9f92942b364d9586b0ef5912432. Existing camera timeouts
and the earlier reboot protected-store discrepancy are separate unresolved issues. Large pilot
histories still use the existing O(n) replay and can hold the operation slot during deletion.

Continue Phase 4: inspect a deletion preview and cancel; then confirm deletion only for chosen
disposable test captures. Check camera restore and profile selection independently. Phase 5
remains unauthorised. No auto-merge is requested.
