# Phase 4: Questions selectors and bulk removed-question deletion

23 October 2026. Owner requested no timezone field on Questions, source selector
buttons, counts and multi-selection for removed questions, mandatory data erasure,
camera names and less vertical padding. No real recorded data was deleted by the agent.

## Changed files and behavior

- `src/vop/dashboard.py`: Questions uses named source links with an All sources button
  and current-selection state, with no timezone/date controls. Ignore irrelevant date/
  timezone parameters for this configuration page and avoid replaying temporal history.
  Filter both current and removed question lists. Use camera names in current question
  labels; other pages retain their timezone controls. Scope compact cells/buttons to
  Removed questions.
- `src/vop/removal.py`: list counts for answers, images, episodes and alerts across all
  question versions; label shared images and show camera names. Native checkboxes belong
  to a separate bulk-selection form, avoiding nested Restore forms. Restore stays a
  separate, recoverable action. Initial selection only opens a deletion preview.
- Permanent single and bulk deletion always purges recorded data; remove the keep-data
  option. Preview camera/question names, per-question counts, shared-image impact and
  reserved IDs. All selected questions must still be removed and the complete preview
  fingerprint must match before any write. Recompute shared runs after each purge, so
  deleting a later question cannot resurrect an earlier answer from a stale raw result.
  Use one SQLite transaction for the batch, existing observation/alert locks, source
  preview clearing and checkpoint handling. Preserve unselected normalised answers,
  immutable definitions/reserved IDs and audit records; old backups/exports are unchanged.
- `tests/test_removed_question_bulk.py`: selector names/filter/no-timezone behavior,
  list counts, external checkbox form association, same/shared captures and multi-version
  deletion, cross-camera same question IDs, cache clearing, restart non-resurrection,
  stale confirmation, rollback after the second purge, restored/active-item guards,
  permissions/CSRF/origin/mode checks, invalid selections and existing busy safeguards.
- `tests/test_question_data_deletion.py`, `tests/test_removal.py`: change previous
  optional/history-preserving expectations to mandatory purging, while retaining tests
  for other answers, alerts/deliveries, gaps, images, rollback, restart and backup restore.
- README and CHANGELOG describe the revised destructive behavior and confirmation flow.

## Commands and observed results

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_removed_question_bulk.py tests/test_removal.py tests/test_question_data_deletion.py`:
  16 passed in 17.91s on the final targeted regression set.
- Earlier `.\.venv\Scripts\python.exe -m pytest -q`: 360 passed, 4 skipped in 89.70s,
  before the final cross-camera regression and snapshot-list/wording refinements.
- `git diff --check`: passed.

- Final `.\.venv\Scripts\python.exe -m pytest -q`: 361 passed, 4 skipped in 76.91s.
- Authenticated managed restart: HTTP 202, new instance ready, camera enabled/image-
  saving/interval controls preserved; observations 15685 -> 15687 while existing
  monitoring drained/resumed. No user deletion was submitted.

CI results are tracked with this change's PR.

## Limits and next acceptance

Destructive tests ran only against disposable synthetic databases, synthetic frames
and fake credentials. No user question/data deletion, camera connection, image review,
model download, GPU benchmark or real browser visual test was performed. No model or
runtime changes; historical approved revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Counts are per question, not distinct across rows. Bulk deletion can remove shared
images/raw details from unselected questions while keeping their typed answers; the
preview explains this. Definitions and IDs remain reserved to prevent seed/restart
resurrection. The existing native form size limit and observation/alert busy guards
remain. Removed questions under retired cameras still require restoring the camera
first, as before. Previously deleted definitions with intentionally retained history
are not retroactively purged by this update.

Refresh Questions, check names/counts and preview a multi-selection without confirming
unless erasure is intended. Continue Phase 4 manual acceptance; Phase 5 remains
unauthorised. Do not auto-merge.
