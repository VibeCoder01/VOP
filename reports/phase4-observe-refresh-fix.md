# Phase 4: Observe refresh and engine result layout

22 October 2026. Follow-up to the owner's foreground preview and formatting requests.

## Cause and changes

The shared browser Content Security Policy used `default-src 'none'` without a
`connect-src` directive. This blocked the Observe script's same-origin fetch requests,
including preview lease renewal and latest-frame checks. The running app's JSON health
response confirmed the missing directive before applying this fix. Script unit tests
had not covered the page response policy.

- `src/vop/browser_auth.py`: allow `connect-src 'self'`; keep other origins blocked,
  images/scripts restricted to self, and all operator/origin/CSRF controls intact.
- `src/vop/dashboard.py`: decode the replacement image off-screen before atomically
  replacing the displayed image. A failed download/decode keeps the prior picture and
  displayed frame ID, so the next poll retries. No document reload, answer-panel swap,
  inference change, image recording or new camera acquisition path.
- `src/vop/integration_ui.py`: put Check again and Back to Engines in the existing
  wrapping actions row; style Back to Engines as a secondary button.
- `tests/test_observe_image_refresh.py`: delayed image decode, successful replacement,
  failed decode/retry, unchanged-frame suppression, monitoring rings and hidden tabs.
- `tests/test_observe_images.py`: page-policy regression and engine footer markup.
- `README.md`, `CHANGELOG.md`: document image-only updates and one refresh after upgrade.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_refresh.py tests/test_observe_images.py tests/test_live_previews.py`:
  10 passed in 3.44s.
- `.\.venv\Scripts\python.exe tools/preview_smoke.py`: PASS. Five explicit synthetic
  frames, masks verified, inference slot held, expired lease closed the child. No cameras
  connected or model weights loaded.
- `git diff --check`: passed.

- `.\.venv\Scripts\python.exe -m pytest -q`: 347 passed, 4 skipped in 71.95s.
- Applied through authenticated managed restart: HTTP 202, new instance ready,
  camera enabled/evidence/interval settings preserved; observations 7903 -> 7905
  while existing monitoring drained/resumed. New JSON response policy confirms
  `connect-src 'self'`. No private images or camera credentials inspected.

CI results will be checked on the pull request.

## Limits and next acceptance

The JavaScript check uses a Node DOM harness and the response policy uses TestClient;
no real browser visual check or live camera/frame-rate benchmark was performed.
The existing 5 fps decoder target and 0.2-second checks are settings, not measured
camera-to-screen performance. No GPU/model/runtime change; approved historical model
revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Refresh Observe once to load the new policy/script, then confirm pictures advance
without refreshing the page and Show answers remains open. Continue Phase 4 manual
acceptance; Phase 5 remains unauthorised. Do not auto-merge.
