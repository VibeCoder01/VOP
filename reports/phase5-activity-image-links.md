# Activity image viewing — 30 October 2026

Completed Save image entries now offer **View image** in Activity and its automatic
row refresh. The link opens the existing observation detail page at Recorded image,
using the job's observation/source identity. It does not open the latest camera
preview or fetch a new frame. Links survive deletion of the action definition as
long as the observation image is retained. Deleted/expired images or observations
show an unavailable message instead of a link. Races after rendering are handled
by the existing detail page's missing-image message.

Existing operator-only evidence access is preserved: viewers get an explanation
instead of a button, and direct image requests remain forbidden. One bounded SQL
metadata query checks saved-image existence across the latest 100 jobs, without
reading image blobs, loading full observation results or replaying histories.

Changed `src/vop/actions_ui.py`, existing `tests/test_save_image_action.py`, README,
Actions runbook, changelog and package version **0.6.10**. No new route, dependency,
schema, capture or image-retention operation was added.

## Validation

- `.venv\Scripts\python.exe -m pytest -q tests/test_save_image_action.py tests/test_actions.py`:
  **26 passed in 16.82 seconds**. Synthetic frames/intercepted delivery only. Checks
  exact saved bytes after newer captures, Activity page/fragment links, viewer
  restrictions, action-definition deletion and image/question-history deletion.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.10**; `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `git diff --check`: passed. Managed restart: **HTTP 202**, new instance **ready**,
  three sources' monitoring, evidence-retention and capture-interval controls unchanged.
- Full CI status is recorded on the PR. No passing PR or main push check is assumed
  without observing its result; these are distinct workflow runs.

No live browser visual/imagery inspection or manual camera, model/GPU, Tapo, audio,
microphone, email/SMS tests were run. No live action or automation was created.
Model revision and hardware measurements are unchanged. Existing retention may
remove an image before a user follows the link; no alternate image is substituted.
Remain in Phase 5 and validate using an owner-triggered Save image action. Phase 6
is not started and no PR is auto-merged.
