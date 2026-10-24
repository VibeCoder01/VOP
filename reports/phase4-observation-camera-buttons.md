# Phase 4 — observation history camera buttons

Date: 24 October 2026

## Change and files

- `src/vop/dashboard.py`: share the existing Observe multi-select camera buttons with
  Individual and Continuous Observations. All cameras resets the selection; choosing
  a camera toggles it. Display current names and omit retired cameras from buttons.
  Preserve every source parameter on Older answers. Show image-saving information
  and existing Configure-only history deletion actions separately for selected cameras.
  Continuous Observations uses workspace timezone and ignores obsolete timezone/date
  query fields. Skip its unused temporal-summary replay during page rendering.
- `src/vop/storage.py`: optional tuple source filters for observations/events, applied
  in parameterised SQL before the global ordering and limit. Existing scalar-source
  callers keep their behavior. No pagination by merging already-limited camera lists.
- `tests/test_history_camera_buttons.py`: three synthetic sources with interleaved
  answers/episodes verify multi-selection, deselection, reset, camera names, invalid
  IDs, timezone removal, global ordering/limit, pagination and unchanged controls.
- `tests/test_history_deletion.py`: verify retired cameras stay absent from buttons,
  historical deep links remain valid and restoration returns cameras to the buttons.
- `README.md`, `CHANGELOG.md`, this report: usage, validation and limits.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q`: **379 passed, 4 skipped** in 134.86s.
- `git diff --check`: passed.
- Authenticated managed `POST /ui/restart`: HTTP 202; new instance ready, source
  monitoring/evidence/interval settings preserved. Observation count 25252 -> 25256
  while existing authorised monitoring drained/resumed. No deletion was submitted.
Initial targeted failures were obsolete dropdown assertions and the new test's exact
camera label expectation (episode labels also include version). Updated those checks
to inspect the new buttons and camera-name portion; no production behavior was
changed to satisfy incorrect expectations.

CI is tracked with this change's PR.

## Limits and next acceptance

Synthetic/offline fixtures only; no new camera connection, model download, GPU run,
user-data deletion or browser visual test was initiated. Model/runtime selection is
unchanged; historical approved revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Selection is URL-based. New selections start at newest answers; Older answers retains
all selected cameras. All cameras includes existing historical records, as before;
retired cameras have no selection button. Existing deep links for a single retired
camera remain valid on Individual Observations. Continuous Observations still shows
the latest 100 matching episodes, without adding episode pagination. Selecting the
last selected camera again returns to All cameras. Trends timezone control is unchanged.

Refresh both observation pages for Phase 4 acceptance. Phase 5 remains unauthorised.
Do not auto-merge.
