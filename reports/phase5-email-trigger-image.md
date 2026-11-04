# Phase 5: Email triggering image and frame identity verification

## Changes

- src/vop/actions.py: email `{image}` marker retains the exact observation/run/frame evidence atomically at enqueue, using Save image; render text fallback and escaped HTML with one inline PNG shared by repeated markers. Sending resolves only the exact saved frame, checks source identity, and blocks if deleted/missing. No queue BLOB/copy, fallback frame, new capture, or separate persistence schema. Existing custom subjects/text-only messages preserved; corrected new default subject to include trigger in editor and validation.
- src/vop/actions_ui.py: image-email camera test selector, marker instructions and retention/missing-image explanation; removed outdated text-only email help.
- tests/test_email_image.py: distinct red/green/blue synthetic frames; exact byte and privacy-mask pixel checks; newer-frame non-substitution, deletion, blocked missing frame, manual test without capture, suppression and atomic rollback.
- tests/test_save_image_action.py: email editor help expectation updated; existing Save image exact-frame and atomic deletion tests retained.
- README.md, docs/actions.md, CHANGELOG.md: usage and limitations.

## Validation

`.venv/Scripts/python.exe -m pytest -q tests/test_email_image.py tests/test_save_image_action.py tests/test_actions.py tests/test_activity_filters.py tests/test_action_browser.py tests/test_deletion_cleanup.py tests/test_workspace_backup.py` — **59 passed in 37.78s** before adding the final suppression/rollback case.

`.venv/Scripts/python.exe -m pytest -q tests/test_email_image.py` — **4 passed in 4.07s**, including the final suppression/rollback case. `git diff --check` passed.

Save image resolves context.observation_id → observations.run_id → runs.frame_id → frames[source_id,frame_id]. A matching temporary privacy-masked frame is used only when the frame ID matches exactly; otherwise it reuses that frame's existing evidence or reports unavailable. The new tests use this same saving path and prove the saved green image remains green after a blue observation replaces the previews. No pre/post substitution occurred in these offline tests.

## Limits / deployment

No real camera, GPU/model, email/SMTP server, Tapo, sound or SMS was contacted. SMTP is intercepted; only synthetic images used. No new model measurements or revision. Service not restarted and live browser appearance not checked. Version remains 0.6.16 within the existing unmerged Phase 5 PR. CI unverified.

Images are privacy-masked source frames, as for normal image saving; question-specific include/exclude/ROI is not reflected in shared saved images. `{image}` explicitly retains the frame even if automatic image saving is off, following existing retention/deletion. Mail clients can display inline PNGs as attachments. Local deletion cannot recall a sent email. Existing queued snapshots are unchanged. Next: finish Phase 5 review/CI and restart via Start VOP; no Phase 6 work.
