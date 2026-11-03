# Phase 5 — Camera overview and retired-camera deletion (3 November 2026)

Version **0.6.15**. The owner requested camera overview columns and an option to
permanently delete a retired camera and its data. No live camera deletion was
performed. Remain in Phase 5; no Phase 6 or auto-merge.

## Changes

- `integration_ui.py`, `dashboard.py`: compact, horizontally scrollable camera
  table with name, model/type, monitoring state, target interval, target samples/hour,
  enabled/total questions, saved keep-open policy, automatic image saving,
  privacy-mask count and last observation-image time. One Manage camera button.
  Four metadata queries; no image/history replay, credential decryption, capture,
  stream startup or network check when listing. Rates use one decimal; durations
  use H:M:S. Disabled/paused/no-enabled-question cameras show target 0.0.
- `camera_deletion.py`, `removal.py`, `service.py`: Retired Cameras retains Restore
  and adds Delete permanently, a scoped data-count preview, typed `DELETE`, and the
  existing indeterminate deletion dialog. Wait off the event loop for the pipeline,
  notification and action guards. Delete source-specific questions/versions,
  policies, images/frames, runs, answers/gaps, episodes, notifications/deliveries,
  Activity, automations and rules, plus profiles and caches. Reusable actions/audio
  and other cameras remain. Remove old revision state if a rule moved to another
  camera, preserving its other-camera revisions/state. No per-image Python loop.
- `storage.py`, `pipeline.py`, `integration_ui.py`: minimal reserved/deleted source
  IDs prevent bootstrap/profile/retained-record reconstruction and UI restore.
  Automatic new-camera IDs skip reserved IDs; stale editor submissions explain how
  to add a replacement. Drop camera entries from authoritative workspace bootstrap.
- `secret_cleanup.py`: include current/retired runtime adapter settings when
  determining shared secret ownership, including cameras without GUI profile rows.
  Unused endpoint/account values use existing durable cleanup; shared values remain.
  If cleanup is pending, the deletion result says it will retry automatically.
- `tests/test_camera_overview_delete.py`, `tests/test_observe_camera_selection.py`:
  passive listing, rate/disabled/paused/USB states, flags, permissions, confirmation,
  fully populated synthetic purge, other-camera/Action preservation, shared-key
  protection, integrity audit, rule-revision cleanup, restart non-resurrection and
  replacement-ID regression. Update the old card-layout assertion to table layout
  while retaining Manage camera/button/scroll-container checks.
- README, changelog, phase plan and project version updated. No new dependency,
  database schema version, model change or new acquisition behaviour.

## Verification

- `.venv\Scripts\python.exe -m pytest -q`:
  **551 passed, 6 skipped in 400.66 seconds**. Existing skips are Windows-inapplicable
  Linux helper/Secret Service tests. This run preceded the final historical-rule-state
  guard; its dedicated case is included in the final targeted command below.
- Final `.venv\Scripts\python.exe -m pytest -q tests/test_camera_overview_delete.py tests/test_observe_camera_selection.py tests/test_deletion_cleanup.py`:
  **16 passed in 17.52 seconds**, including old/new rule revision state preservation.
- `.venv\Scripts\python.exe -m pytest -q tests/test_camera_overview_delete.py tests/test_unified_camera_settings.py tests/test_deletion_cleanup.py tests/test_removal.py tests/test_history_deletion.py`:
  **38 passed in 53.21 seconds**, before the final rule-state regression additions.
- An initial focused purge test caught non-reentrant Actions cache cleanup while
  its guard was held; cleanup now runs after releasing that guard. An initial full
  run had one stale card-selector assertion (550 passed, 1 failed, 6 skipped);
  it was updated for the requested table layout and the subsequent full run passed.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.15**. `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `git diff --check`: passed.

Local activation: the read-only health probe found port 8765 unavailable
(`ConnectionRefusedError`), and process inventory found **no run_dashboard.py
processes**. No reload request was sent, and VOP was not started automatically.
Open **Start VOP** to load the installed update; this may resume saved monitoring
and automations. Live UI activation is therefore not verified.

All deletion tests used disposable synthetic DBs, mock inference and fake protected
values. The successful purge test ran the read-only deletion integrity audit: PASS,
and verified other-camera frames/Activity and a shared credential remained while
the deleted camera's unused endpoint disappeared. No actual camera/retired camera,
live data or real vault value was deleted. No live browser/image inspection, manual
camera/GPU inference, model download, device action/audio/email/SMS or benchmark
was performed. No model/runtime measurements changed; pinned d1-3B revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

## Boundaries / recommendation

Target samples/hour is planned effective rate, not achieved throughput. The keep-open
column is configuration, not proof of a live connection; use Diagnostics for health.
Save images is automatic recording; explicit Save-image actions may retain captures
independently. Privacy masks are camera-wide, separate from question areas.

Only retired RTSP/USB cameras can be purged. Data removal is atomic; the progress
indicator is deliberately not a fabricated percentage. OS-vault cleanup may remain
durably pending if work/permissions prevent it; VOP retries. Minimal reserved IDs
and audit history remain. Existing backups/exports and already-sent messages are
unchanged; restoring an older backup is an explicit separate operation.

Use the installed overview after starting VOP and choose permanent deletion only
for a camera you intend to purge. CI must be verified on the PR and any later merged
main push separately. No CI result is presumed and no PR is auto-merged.
