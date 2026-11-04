# Phase 5: Activity column filters

Version 0.6.18 puts native filter controls under the four table headings. Queued at has inclusive GMT/UTC dates; Automation / action has the two existing selectors; Result has a selector; Details has a case-insensitive literal substring search. Apply filters (or Enter) submits a read-only GET; Clear filters resets the query. Existing SQL filtering before LIMIT 100 remains. The query survives automatic and manual refresh.

Only tbody rows refresh. The column headings and controls are outside the refresh target, so polling cannot remove typed values or focus. The rows endpoint now returns rows rather than a nested whole table; empty matches and invalid dates are valid four-column rows. Existing viewer/operator permissions and image access remain unchanged.

Changed files: src/vop/actions.py, src/vop/actions_ui.py, src/vop/dashboard.py, tests/test_activity_filters.py, tests/test_actions.py, README.md, CHANGELOG.md, pyproject.toml, this report.

Validation: `.venv/Scripts/python.exe -m pytest -q tests/test_activity_filters.py tests/test_actions.py tests/test_save_image_action.py tests/test_email_image.py tests/test_action_browser.py` — **33 passed in 22.70s**. Tests cover filter placement, no controls in the refresh body, literal Details search including percent, filtering older-than-100 records, selection persistence, date validation, action permissions, image identity and browser audio. An old fragment test expected a whole table; updated to expect a row fragment while retaining permission and document-shell checks.

`git diff --check` passed. `.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .` installed 0.6.18. No real cameras, model/GPU, device actions, audio playback, SMTP or SMS used; no new hardware measurements or model revisions. Live UI appearance and CI unverified. Service not restarted; use Start VOP to load code. Continue Phase 5 review/CI; Phase 6 remains unauthorised.

Spacing correction: browser CSP style-src self rejects inline style attributes. Replaced the ineffective inline margin with the activity-pause stylesheet class and 12px bottom padding. Offline Activity filter test passes; no security-policy change.
