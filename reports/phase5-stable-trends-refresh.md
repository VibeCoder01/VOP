# Phase 5 stable Trends refresh — 30 October 2026

The ten-second Trends timer used `location.reload()`, rebuilding the entire page and
all its graph controls. It now fetches the same authenticated page in the background,
parses it without running its scripts, and updates the existing canvases, numeric
figures and episode summaries. The page and filter/control elements stay in place.
Historical windows, Fit/Latest behaviour, scroll/zoom lock and canvas focus persist.

Numeric graph slots exist even before the first observation, so receiving the first
result does not insert a new toolbar/plot above later questions. Figures retain their
previous height when placeholder text shrinks to a number. A fixed-height status area
reports temporary failures without throwing away visible results. Only one refresh
request runs at a time; visibility, filters, interaction and expiry are checked both
before the request and after its response. Non-navigation Accept semantics preserve
401 handling by the shared session guard instead of following a login redirect.

Question IDs/versions and section counts must still match before patching. If another
tab changes question configuration, a message asks the owner to use Refresh now to
load the changed layout. Network failures retain the old view and retry. Categorical
Choice statistics update too; Choice still has no numeric graph. No new endpoint,
dependency, schema, acquisition, inference or history deletion is added.

## Changed files and validation

- `src/vop/dashboard.py`: in-place timer, patch targets and status area.
- `src/vop/trends_ui.py`: empty graph slots, mutable data/redraw API, metric patching
  and retained control instances. `README.md`, `CHANGELOG.md`, `pyproject.toml` and
  this report document **0.6.8**. Navigation and refresh regression tests updated.
- `.venv\Scripts\python.exe -m pytest -q tests/test_trends_navigation.py tests/test_trends_refresh.py tests/test_phase2_browser_storage.py`:
  **19 passed in 18.35 seconds**. Offline TestClient/Node fake-DOM contracts cover
  existing canvas/control identity, unchanged page scroll, live figures and reserved
  heights, history/follow-latest state, empty-to-first-result, sync, unknown gaps,
  request coalescing, mid-response interaction, filter edits, retry, changed-layout
  handling and expiry. The refresh contract asserts zero page reloads.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.8**. `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `git diff --check`: passed; Windows line-ending notices are informational.
- Managed local restart: **HTTP 202**, a new **ready** instance; all three sources'
  monitoring, evidence-retention and capture-interval controls unchanged.
- `.venv\Scripts\python.exe tools/audit_deletions.py --check-vault`: **PASS** after
  restart; all 17 database issue counts, pending cleanup and unused canonical/legacy
  protected-file counts are zero. The audit is read-only.
- Final full Windows/Ubuntu CI results are recorded on the pull request, without
  assuming success in advance.

No live browser visual inspection, manual camera, GPU/model, microphone, physical
action, audio, email/SMS or benchmark tests were performed. Existing authorised
monitoring may continue. The model revision remains unchanged; no new hardware or
accuracy measurements are claimed. This retains the existing full-history replay
and full selected-range HTML payload cost. Apply date filters to limit large ranges.
Remain in Phase 5 and confirm normal reading/navigation in the owner browser; Phase
6 is not started and no PR is auto-merged.
