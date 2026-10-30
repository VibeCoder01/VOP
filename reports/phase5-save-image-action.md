# Phase 5 Save image action — 30 October 2026

Configure → Actions now offers **Save image**. Name and save it, then select it in
an automation. It retains the privacy-masked, metadata-stripped, downscaled PNG for
the observation used to evaluate the trigger, in the existing `frames.evidence_png`
column. Individual Observations sees it through the normal evidence join. This is
the same source preview as normal automatic saving, not a per-question ROI/mask
rendering. Source automatic-save controls remain unchanged.

The accepted local image operation and completed/blocked Activity receipt, including
action-result audit, commit in the same SQLite transaction. Schedule, cooldown,
hourly limits, synthetic suppression and duplicate checks run before any image write.
Normal external actions retain their existing asynchronous delivery queue. No image
payload enters that queue, Activity context, files or a new cache. There is no hidden
later image write to restore evidence after deletion or restart. Action deletion does
not delete observation history; normal image/retention/question-data deletion does.

The context pins an observation ID. Existing saved evidence is reused; otherwise
only an exact frame-ID match in the existing processed/capture previews can be saved.
If the preview is no longer available, Activity reports blocked, without taking a
capture or substituting a newer frame. This limitation is visible in setup help.
Manual Test action requires a camera selector and uses its latest captured observation;
with no image/observation it reports blocked and asks for an observation first.

Email was inspected and its intercepted SMTP contract checked: it constructs a
plain-text `EmailMessage` with no attachments. The editor/help/README now explicitly
say that linking Save image and Email does not attach the image. Email attachments
were not requested or implemented.

## Files and validation

Changed Actions definitions/evaluation/test/local adapter in `src/vop/actions.py`,
forms/help in `src/vop/actions_ui.py`, image-saving explanations in `dashboard.py`,
new `tests/test_save_image_action.py`, SMTP attachment assertion in `test_actions.py`,
README, Actions runbook, changelog, Phase 5 scope note and version **0.6.9**.

- `.venv\Scripts\python.exe -m pytest -q tests/test_save_image_action.py tests/test_actions.py tests/test_automation_markers.py tests/test_deletion_cleanup.py tests/test_history_deletion.py tests/test_question_data_deletion.py`:
  **50 passed in 36.39 seconds** after final audit/UI changes. All frames are
  synthetic and email delivery is intercepted. Covers pixel privacy, identical
  canonical PNG, unchanged source controls, automatic dedup/suppression, missing or
  replaced previews, existing evidence, atomic rollback, image deletion, question-data
  deletion, restart persistence, manual form validation and zero email attachments.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.9**; `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- Managed restart: **HTTP 202**, new instance **ready**, all three sources' monitoring,
  retention and capture-interval controls unchanged. No Save image action or automation
  was created in the owner's live configuration by this work.
- Full Windows/Ubuntu CI and final read-only deletion audit results are recorded on
  the pull request. `git diff --check` passed; no new dependency or schema was added.

No live browser visual inspection or manual camera, GPU/model, Tapo, audio/microphone,
email or SMS test was run. Existing authorised monitoring may continue. Model revision
is unchanged; there are no new hardware/accuracy measurements. Delayed automations
may find their unsaved frame has already left the bounded preview cache; this is
reported rather than saving a different frame. Existing history-replay costs are
unchanged. Remain in Phase 5 and use an explicit owner-triggered image test/automation
for acceptance. Phase 6 is not started; no auto-merge.
