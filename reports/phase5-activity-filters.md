# Phase 5: Activity filters and timestamp clarity

Activity now labels its recorded timestamp **Queued at**, with an explanation that this is not device request/completion time. Independent GET filters select action, automation, result and inclusive GMT / UTC date range. Parameterized SQL filters before LIMIT 100; historical action/automation names remain selectable. Automatic fragment refresh and manual refresh preserve the query. Clear filters restores the unfiltered view. Invalid or reversed dates show a correction message. Existing compact wrapping filter styles are reused.

Changed: src/vop/actions.py, src/vop/actions_ui.py, tests/test_activity_filters.py, README.md, CHANGELOG.md, pyproject.toml, this report.

Validation: `.venv/Scripts/python.exe -m pytest -q tests/test_activity_filters.py tests/test_actions.py tests/test_action_browser.py tests/test_save_image_action.py` — 28 passed in 16.36s. Tests cover a match older than the first 100 records, combined filters, inclusive date boundaries, invalid dates, parameterized values, selected form values and refreshed fragments. Existing action, browser sound and saved-image tests remain included.

No live cameras, model weights, GPU, Tapo devices, audio output, email or SMS were used. No new model measurement or revision. Live browser appearance and CI are unverified. Filtering is read-only; the service has not been restarted. Device completion timestamps are not stored, so only queued timestamps are shown. Next: remain within Phase 5; review CI and reload through Start VOP when convenient. No Phase 6 work.

Automation trigger descriptions now include the configured Yes/No, choice or ordinal threshold (label and number), or active duration. The list also names the question. New email subjects include {trigger}; the original default subject gains it when sending. Custom subjects are preserved. Existing queued messages are unchanged.

Final validation after the trigger fixes: `.venv/Scripts/python.exe -m pytest -q tests/test_actions.py tests/test_activity_filters.py tests/test_action_browser.py tests/test_save_image_action.py` — **29 passed in 16.24s**. SMTP was intercepted; no real email was sent. Tests cover complete binary/choice/ordinal/duration descriptions, the automation list, queued trigger context, legacy default subject expansion, and preservation of custom subjects. Additional changed file: tests/test_actions.py.
