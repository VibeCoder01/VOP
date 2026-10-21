# Optional recorded-data deletion for a removed question — 21 October 2026

The existing Delete removed question page now includes an unchecked Also delete all recorded
data for this question option. The page previews answer/image/episode/alert counts across
all versions, identifies shared images and explains the effect on other results. Default
configuration-only deletion still preserves recorded history.

Selecting the option deletes that question's observations (including timestamp-only deletion
gaps), episodes, alerts and delivery records. It deletes exclusive capture runs/frames and
clears associated retained image bytes on shared frames. Other questions' normalised answers,
IDs, scores, status and episode measurements are kept. Shared opaque provider payloads,
usage and per-answer raw fields are cleared because they may also contain the deleted
question's answer; that effect is stated before confirmation. Unrelated captures and other
sources are not purged. Question definitions, disabled version pointers, reserved IDs, rule
configuration and audit history remain. Existing backups/exports/sent messages are unchanged.

Recompute the preview fingerprint inside the same immediate transaction as data erasure and
configuration deletion. Missing/stale counts re-render a fresh confirmation, with no changes
committed. Keep operator/Configure-mode/origin/CSRF/version checks and capture/alert locks.
A failure rolls back both recorded-data deletion and configuration deletion. Clear the
in-memory source preview after commit, use existing SQLite secure_delete and the existing
WAL checkpoint behavior. Reuse alert/rule cleanup and checkpoint helpers for the existing
capture/source deletion paths; their behavior is unchanged.

Changed files: `src/vop/history_deletion.py`, `src/vop/removal.py`,
`tests/test_question_data_deletion.py`, `README.md`, `CHANGELOG.md` and this report.
No dependencies, schema migration, inference contract or model revision changed.

Windows validation commands/results:

- `.\.venv\Scripts\python.exe -m pytest tests/test_question_data_deletion.py tests/test_removal.py tests/test_history_deletion.py -q`:
  19 passed in 26.20 s (two initial new tests plus existing destructive-path tests).
- `.\.venv\Scripts\python.exe -m pytest -q`: 317 passed, 4 skipped in 135.14 s. Skips
  are Linux-only helper tests. The additional default-off preservation regression was added
  after this full run had collected its tests.
- `.\.venv\Scripts\python.exe -m pytest tests/test_question_data_deletion.py -q`:
  all three new tests passed in 4.68 s on the final test revision. They cover multi-version
  answers, shared/exclusive/unrelated images, raw-payload erasure, preservation of all other
  typed answer fields, other-camera isolation, alerts/deliveries, old deletion gaps,
  preview invalidation, CSRF/viewer/View-mode/busy denial, transactional rollback, restart,
  backup/restore, foreign-key integrity, and unchanged answers/images when unchecked.
- `.\.venv\Scripts\python.exe tools/phase2_smoke.py`: PASS; synthetic input, explicit mock,
  native session/CSRF, replay, six views, viewer image denial 403, deleted image denial 404
  and 21 answers persisted across restart. No live cameras connected.
- `git diff --check`: passed.

Applied via the authenticated restart endpoint. A new instance returned healthy, preserving
all source enabled/image-saving/interval controls. Existing user-configured monitoring
drained/resumed; observation count increased from 3922 to 3924. No live user question or
recorded data was purged: destructive testing used isolated synthetic/mock fixtures only.
No manual camera, Antec, real-model or GPU test was run and no benchmark is claimed.
Historical approved d1 revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Limits: saved images are shared by captures, so purging them also removes the images from
other answers on those captures; the confirmation shows this explicitly. Raw engine data
from those shared captures is cleared while other normalised answers remain. This option
applies before permanently deleting the question's configuration. Definitions/audit records
and existing external copies remain. Continue Phase 4 pilot use; Phase 5 is unauthorised.
