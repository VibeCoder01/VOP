# Phase 5: Collapsible Activity question groups

Version 0.6.20. Activity action records are grouped by source ID and question ID across question versions. Camera friendly name and question text label each summary, together with matching action count and latest queued time. Groups and their records are newest-first. Each native Details starts closed. Polling snapshots open group keys and restores them after replacement; new groups remain closed. Manual tests lacking question identity use separate action/camera keys rather than being confused with question events.

Existing action/result/date/details filters are applied before grouping and before LIMIT 100. Counts represent matching records within that bounded result, not all-time totals. Existing per-action statuses, timestamps, detail text, image links and operator-only edit links remain inside each expanded group. No acquisition/inference/storage schema changes.

Changed files: src/vop/actions_ui.py (group rendering and refresh preservation); src/vop/dashboard.py (compact group styles); tests/test_activity_question_groups.py (new); README.md; CHANGELOG.md; pyproject.toml; this report.

Validation: `.venv/Scripts/python.exe -m pytest -q tests/test_activity_question_groups.py tests/test_activity_filters.py tests/test_actions.py tests/test_save_image_action.py tests/test_email_image.py tests/test_action_browser.py` — **35 passed in 19.78s**. Includes source/question identity isolation, grouping across versions, newest order, collapsed default, filtered counts, manual-test separation and Node fake-DOM preservation of expansion while new groups stay closed. Existing permission/image/browser-action checks included. `git diff --check` passed. Editable pip installation uses `--no-deps --no-build-isolation -e .` for 0.6.20.

No real cameras, GPU/model weights, device actions, SMTP, SMS or audio playback were used; no new model revision/measurement. Live browser appearance and CI unverified. Service not restarted; Start VOP loads update. New page loads intentionally start collapsed; expansion is retained during that page's polling, not across navigation. Next: Phase 5 review/CI; Phase 6 not started.
