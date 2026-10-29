# Phase 5 Trends navigation — 29 October 2026

Trends now renders all numeric samples in the selected date/camera range at their
actual UTC positions, labelled in the workspace timezone. Native horizontal scrolling,
dragging, Earlier/Later, a 1–1024× Zoom slider, Fit and Latest provide time navigation.
Arrow keys, +/−, Home/End and Ctrl + wheel are supported. The optional Lock scroll
and zoom checkbox applies the same absolute time window to all displayed graphs.

Per-tab session storage preserves independent or locked windows across the existing
10-second refresh. Historical windows stay fixed; Latest follows new records (rather
than a date filter's future midnight). Fit expands with new data. Changing filters
resets navigation. Refresh checks interaction/filter state before and after health
preflight, saves navigation before reloading, and waits during dragging or recent
navigation. Session expiry still stops reloads through the existing guard.

Canvas rendering uses binary searches and draws the visible sample slice plus its
neighbours; large views omit individual dots. Common bounds use chronological series
endpoints. Failed/unknown samples and declared gaps break the line and shade unknown
time. No acquisition, inference, new endpoint for data, dependency, schema migration or
plotting framework is added. Without JavaScript/canvas the static preview shows up to
200 recent samples in sample order; interactive graphs use timestamp spacing.

The Configure Questions list also marks questions with Include, Exclude or advanced
ROI areas using an asterisk with a descriptive tooltip. Clearing all question areas
removes it; camera privacy alone does not add it. Processing order is unchanged:
camera privacy, question includes/excludes (exclude wins), optional ROI crop.

Changed files: new `src/vop/trends_ui.py`; dashboard integration, browser asset
authorization and question-list markup in `dashboard.py`, `browser_auth.py` and
`removal.py`; new `tests/test_trends_navigation.py`; refresh, browser asset and mask
tests; README, image-mask runbook, changelog and package version **0.6.7**.

## Validation

- `.venv\Scripts\python.exe -m pytest -q tests/test_trends_navigation.py tests/test_trends_refresh.py tests/test_question_masks.py tests/test_phase2_browser_storage.py`:
  **43 passed in 22.25 seconds**, including the final future-date Latest refinement.
  Node fake-DOM/canvas checks cover true timestamp spacing, gap breaks, independent
  navigation, locked time windows, programmatic-scroll feedback, pointer cancellation,
  persistence, follow-latest and visible-slice rendering of a synthetic 20,000-point series.
- `.venv\Scripts\python.exe -m pytest -q`: **506 passed, 6 skipped in 290.45
  seconds**, started before the final future-date Latest refinement covered by the
  focused run above. Skips are four Linux-only remote-helper tests and two Linux
  Secret Service contracts on Windows. Final Windows/Ubuntu CI results are recorded
  on the pull request.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.7**; `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `git diff --check` and Python compile checks passed.
- Managed local restart: **HTTP 202**, new instance **ready**, three source controls
  (monitoring enabled, image retention and sample interval) unchanged.
- `.venv\Scripts\python.exe tools/audit_deletions.py --check-vault`: **PASS** after
  restart, zero issues in all 17 database checks, zero pending cleanup or unused
  canonical/legacy protected files. Read-only; no history was deleted.

No live browser visual inspection, manual camera capture, microphone, Tapo action,
audio, email/SMS, GPU/model or benchmark test was performed. The pinned model revision
is unchanged and no new hardware measurements are claimed. Existing authorised
monitoring may continue. Categorical Choice answers still have no numeric trend graph.
All selected samples are transmitted with the page; restrict dates for very large
histories. The existing full-history temporal replay cost remains unchanged.
Stay within Phase 5 and validate the controls with normal owner use. Phase 6 is not
started; no auto-merge.
