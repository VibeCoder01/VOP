# Phase 5 — Selective backup, restore, reset and notification filters

Owner authorised these changes on 2 November 2026. Version **0.6.14**. No live
workspace reset or restore was authorised as part of implementation, and none was
performed. Remain in Phase 5; no Phase 6 work or auto-merge.

## Changes

- `workspace_backup.py`: selective `.vop` archives, SQLite snapshot/pruning/VACUUM,
  checksums, fixed-schema/integrity/reference validation, protected encrypted blobs,
  independently selected restore groups, authoritative workspace bootstrap, and
  restart-boundary DB/vault replacement with persistent rollback/completion journal.
- `workspace_ui.py`: separate configuration/data checkboxes for backup and restore,
  bounded binary upload, expiring preview/counts/cancel, deliberate typed `RESET`,
  restart tracking, worker draining and local sign-in preservation. Saved action
  audio is configuration; retained images/answers and notification/action history
  are captured data. A missing archive group is kept, not interpreted as empty.
- `release_ui.py`, `reliable.py`: default current-only notification filters/results;
  opt-in historical cameras/questions only if they have actual notifications;
  historical labels retained on genuine notifications. Clarify Notification rules
  and VOP notification list terminology. Pause notification evaluation/delivery
  after restore, with an explicit Resume notification rules control.
- `browser_auth.py`, `pipeline.py`: retain operator, mode, CSRF and origin controls;
  one bounded binary upload endpoint accepts its CSRF token in a header. Track and
  drain in-flight HTTP writes before maintenance and reject new work. Replay the
  original receive channel after form parsing rather than falsely reporting a
  disconnect (required for authenticated streamed backup downloads).
- `service.py`, `tools/run_dashboard.py`: apply pending operations only after old
  VOP processes/workers stop, before starting the new server. Clean preview uploads
  on shutdown. Stored workspace state overrides original sample/launcher seeding;
  post-restore edits remain authoritative across restart.
- `integration_ui.py`, `ui_readiness.py`, `operator_workflow.py`, `diagnostics.py`:
  no implicit engine resurrection or reconnect after reset; require engine selection;
  show restored notification pause status/remediation.
- `tests/test_workspace_backup.py`, `tests/test_settings_tabs.py`: disposable
  end-to-end reset/restore, selections, credentials, clips, camera names/masks/options,
  edit persistence, malformed/checksum/schema/path rejection, cancellation, permissions,
  write-drain concurrency, interrupted apply/recovery, and a fake-browser upload /
  restart / preference cleanup contract. No production timer weakening.
- README, CHANGELOG, phase plan and package version updated. No new dependencies,
  schema version or model/backend implementation changes.

## Verification

- `.venv\Scripts\python.exe -m pytest -q`: **548 passed, 6 skipped in 306.38 seconds**.
  Existing skips are Linux-specific remote/helper and Secret Service cases on Windows.
  An earlier full run had one stale assertion for the renamed Rules tab; its expected
  label was updated without removing its functional checks.
- Final `.venv\Scripts\python.exe -m pytest -q tests/test_workspace_backup.py tests/test_settings_tabs.py`:
  **19 passed in 17.09 seconds**, after final browser-preference cleanup, backup-size
  preflight and wording refinements. The full run preceded those small refinements.
- Focused `.venv\Scripts\python.exe -m pytest -q tests/test_workspace_backup.py tests/test_phase3_release.py tests/test_diagnostics.py tests/test_phase2_browser_storage.py tests/test_ui_modes.py`:
  **60 passed in 58.35 seconds**, before the final small refinements.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.14**. `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `git diff --check`: passed.
- Separate local Windows DPAPI check used only `TemporaryDirectory` stores, a
  generated dummy account value and synthetic configuration: protect → selective
  configuration backup → validate → change dummy value → restore encrypted original.
  **PASS**; no real vault, credentials, camera or live workspace was used. It exercised
  `SecretStore(root=temp)`, `create_archive`, `inspect_archive`, `queue_operation`
  and `apply_pending`. Unit tests use an explicitly fake OS-encryption test double.
- Routine managed reload: **HTTP 202**, new instance **ready**; camera IDs,
  monitoring/retention/interval metadata and selected engine identity unchanged.
  Checked that no live maintenance operation was pending before the reload. This
  reload activates code and does not apply a reset or restore.

No live browser HTML/imagery inspection, manual camera/inference, model download,
new CUDA/GPU benchmark, Tapo command, microphone/playback or email/SMS test was run.
Existing enabled monitoring resumes normally after reload. The pinned d1-3B revision
remains `051bcc464b01b9f92942b364d9586b0ef5912432`; no new model/runtime measurements
are claimed. CI is not presumed passed; PR checks and later main-push checks are
separate results.

## Boundaries / next use

The intended workflow passed on disposable data: configuration-only download →
reset → configuration-only restore → cameras/questions/actions/automations/audio
return, with no old captured answers/images. Local sign-in survives reset. Existing
monitoring settings can generate new observations after restore. Automations and
notification dispatch are paused for explicit review; queued messages/actions are
cancelled rather than replayed.

Protected credential restore needs the same Windows user profile on the same
computer. The archive as a whole is not encrypted: ordinary metadata and retained
images/answers are readable. Keep it private. Protected-settings backup on Linux
Secret Service is not implemented; data-only archives do not require that vault.
The UI caps upload/unpacked contents at 2 GB and refuses oversized downloads. Larger
workspaces retain the legacy offline tooling; legacy backups do not include keys.
Restore expects the matching VOP schema/version. Independent-group restore requires
compatible immutable history descriptors and rejects unmatched/orphan references.

Reset removes this workspace's DB data/settings, retired/deleted records, saved
clips, protected VOP values and adjacent migration DB snapshots, but keeps application
files, model files, external input files/downloaded backups, previously sent messages
and the local sign-in key. VOP-prefixed UI preferences are cleared in the completing
browser; other browser sessions are external to the server workspace. Model worker
installation, system environment and SSH/Tailscale setup are external configuration.

Uploads/stages are bounded and cleaned on cancel/expiry interaction/shutdown or
successful apply. Interrupted operations keep a recovery snapshot, recover/retry on
the next managed launch and remove it after completion. Enough local space is needed
for snapshot/staging/rollback; failures keep recovery material instead of claiming
success. Actual power-loss durability, cross-machine DPAPI migration and 2 GB hardware
stress tests were not performed. Validate your downloaded backup preview before
choosing a destructive reset. No further phase is recommended automatically.
