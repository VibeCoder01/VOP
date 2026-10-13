# Phase 2 validation — 13 October 2026

Owner instruction: “Begin Phase 2”, after the owner independently ran the Phase 1 laptop smoke
and obtained PASS. Separately authorised a brief local USB webcam test. Branch `codex/phase-2`
is based on tested `codex/phase-1` (`d48b8be`); PR #2 was still unmerged at commencement.
An initially attempted stacked PR returned base-branch-invalid because the owner had subsequently
merged PR #2 (`4928889`) and deleted its branch. Fetched/pruned remote references and merged the
updated `origin/main` into the development branch; Phase 2 now targets `main` directly. Neither
PR was merged automatically. SRS requirements/IDs are unchanged.

## Implemented and verified software

FastHTML server-rendered desktop/mobile views: overview, sources, questions, events, metrics,
settings and native-result inspection. No external asset request, JS bundle or SPA is needed.
Local operator/viewer sign-in uses a signed HttpOnly/SameSite cookie, CSRF and origin checks.
Bearer API callers remain compatible. Viewers cannot mutate controls, capture or see images.

Question/policy edits create immutable versions. Source controls and mock presets persist;
ROI groups share original frame identity, and privacy masks precede cropping/preview retention.
Evidence is default-off, operator-only, and deletable with matching preview clearing.

Pure replay derives confirmation-based binary states and stable episodes. Failed/unsupported/
missing/stale samples never close an event as negative. Resume, split and manual-review gap
policies preserve unknown intervals; superseded query versions do not pretend negative closure.
Choice dwell and ordinal trends preserve distinct semantics. Counts/estimated durations/rates/
coverage use bounded sampled intervals, UTC arithmetic and local-calendar/DST labels. Date
clipping does not re-activate an episode that began before the selected window. Missing interval
data is not presented as a measured zero. Trend lines break across unobserved gaps.

Explicit background sampling uses one worker, zero backlog, capped source-failure backoff,
audited overload and persistent stop/disable controls. Soft inference deadlines remain the
Phase 1 limitation; a hung injected heavy engine needs process restart/later hard isolation.
SQLite v1→v2 creates a consistent backup, retains observations/versions and supports deterministic
event rebuilding. Late samples are retained/audited but excluded from live temporal processing.

## Exact commands and results

```powershell
git fetch origin
git checkout -b codex/phase-2 codex/phase-1
.\.venv\Scripts\python.exe -m pip index versions tzdata
# Explicitly authorised USB hardware check dependency; not part of CI:
.\.venv\Scripts\python.exe -m pip install opencv-python-headless==4.13.0.92 tzdata==2026.5
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe tools\phase1_smoke.py
.\.venv\Scripts\python.exe tools\phase2_smoke.py
.\.venv\Scripts\python.exe -m pip check
git diff --check
```

Actual host: Windows 11 Pro / Python 3.11.9 Dell, as recorded in Phase 0. Optional capture
packages installed: OpenCV headless 4.13.0.92 and NumPy 2.4.6; timezone data 2026.5.
The default offline closure pins tzdata but excludes optional OpenCV/NumPy camera dependencies.
No Torch/Transformers or model weights were installed/downloaded on the laptop for this phase.

Regression tests progressed from 142 through 150/155/157 to **161 passing tests** (latest added
control tests run: 6.92 s). There were two intermediate implementation/test failures, resolved:
FastHTML requires a plain async-generator lifespan rather than Starlette's context-manager
wrapper; and an overly strict XSS assertion wrongly rejected quoted text inside correctly escaped
`&lt;img ...&gt;`. Actual element injection remains blocked and tested. No failures were hidden.

`pip check`: no broken requirements. `git diff --check`: no errors (ordinary LF/CRLF notices).
Phase 1 actual HTTP smoke still passes. Phase 2 actual HTTP smoke passes browser-session login,
CSRF forms, a confirmed closed synthetic episode, deterministic replay, viewer image denial 403,
deleted-image denial 404, all six views and **21 observations surviving process restart**.
Temporary smoke databases and keys are removed; no camera is opened by either smoke script.

## Real USB test (explicit authorisation; no retained imagery)

Commands used ignored local scripts:

```powershell
.\.venv\Scripts\python.exe .cache\phase2_camera_check.py
.\.venv\Scripts\python.exe .cache\phase2_usb_pipeline.py
```

First script called `SourceAdapters(allow_live_sources=True, timeout_seconds=15).capture`
with USB device index 0. It returned an actual **640×480 PNG**, capture timestamp
`2026-10-13T18:04:04.633438+00:00`. It printed metadata only and saved no pixels.

Second script used a temporary USB-configured app/database and two authenticated capture calls.
Both returned 201/success. Six observations were stored, the rendered dashboard returned 200,
and the binary state was ACTIVE after two preconfigured positives. **Inference was explicit
deterministic MOCK, not real vision.** No evidence BLOB existed; the in-memory preview was cleared
and the temporary database was removed. No real-camera screenshot or image was committed.

This verifies the actual USB acquisition→software→dashboard path. It does not validate whether
the questions were answered correctly from that camera image or establish a new d1-3B result.
The pinned official server CPU model/API result remains the separate Phase 0 evidence.

## Actual browser QA

Used the installed Playwright skill wrapper in a dedicated `vop-phase2` session against an
isolated loopback-only synthetic QA app on port 8876. Its disposable keys/data are ignored.
No private operator credential or real camera data was used. Commands included:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' 'C:/Users/shaun/.codex/skills/playwright/scripts/playwright_cli.sh' -s=vop-phase2 open http://127.0.0.1:8876/login
# Snapshot-derived element references: fill access key, click Open workspace,
# Run synthetic demo, Questions → Edit, edit text/ROI, Save new version, Metrics.
& 'C:\Program Files\Git\bin\bash.exe' 'C:/Users/shaun/.codex/skills/playwright/scripts/playwright_cli.sh' -s=vop-phase2 resize 390 844
& 'C:\Program Files\Git\bin\bash.exe' 'C:/Users/shaun/.codex/skills/playwright/scripts/playwright_cli.sh' -s=vop-phase2 screenshot --filename=output/playwright/phase2-mobile-metrics.png
& 'C:\Program Files\Git\bin\bash.exe' 'C:/Users/shaun/.codex/skills/playwright/scripts/playwright_cli.sh' -s=vop-phase2 console error
```

Actual checks: sign-in/session, navigation, six-step synthetic episode, immutable query edit,
ROI crop grouping and overlay, native result inspection, date/timezone controls, responsive
390×844 layout and desktop layout. Visually inspected screenshots with local image tools.
Browser console error/warning count was zero. Sidebar sign-out contrast and unknown-gap graph
breaks were improved; repeated demos now use actual synthetic acquisition instants rather than
re-inserting earlier timestamps into existing live history. Screenshots/traces are ignored.

## Acceptance and SRS traceability

| Gate | Software result | Evidence |
|---|---|---|
| P2-01 | PASS | Session/login/logout, viewer permissions, CSRF, host/origin denial, escaped text and tampered-cookie tests. |
| P2-02 | PASS | Binary/choice/ordinal immutable editing, confirmations/gaps/threshold/ROI, persisted mock presets, source control UI. |
| P2-03 | PASS | Pure replay, confirmation/closure, unknown/resume/split/manual review, query supersession, stable event IDs. |
| P2-04 | PASS | Counts/durations/rate/occupancy/coverage, category dwell, ordinal gaps, date clipping, zero-vs-missing and repeated DST hour tests. |
| P2-05 | PASS | Default-off masked evidence, operator viewing, actual HTTP viewer 403, deletion 404 and matching preview invalidation. |
| P2-06 | PASS | Actual desktop/mobile browser interaction and masked synthetic ROI preview; no external assets/JS bundle. |
| P2-07 | PASS | One worker/no backlog, stopped/disabled source, drop/audit overload, capped retries, stale/unknown state and no negative source-failure closure. |
| P2-08 | PASS | Transactional schema migration with backup, restart controls/data, immutable versions, replay equality and late-frame audit/exclusion. |
| P2-09 | LOCAL PASS; CI pending | 161 regressions plus two actual HTTP smokes and authorised USB/software check; Windows/Ubuntu CI to be checked after push. |

| SRS scenario | Actual status |
|---|---|
| AT-01 USB | Actual USB and capture→mock→storage→rendered dashboard passed. Real-model camera classification/accuracy remains untested. |
| AT-02 Tapo/RTSP | Adapter, timeout/disconnect/error paths verified with offline fakes. No authorised RTSP endpoint/configuration supplied; hardware test NOT RUN. |
| AT-03 many questions | PASS; three independent answers share a frame, including compatible ROI groups. |
| AT-04 episodes | PASS on deterministic replay and actual HTTP synthetic demo; confirmation opens/closes exactly once. |
| AT-05 disconnect | PASS software; unknown intervals preserve an open/unconfirmed event, never a fake negative closure. |
| AT-06 timezone/DST | PASS UTC interval arithmetic and distinct BST/GMT labels for the repeated local hour. |
| AT-07 evidence/permission | PASS local role boundary/default-off retention/deletion; external backup copies need independent retention policy. |
| AT-08 overload | PASS zero backlog/drop counts and responsive health; no broad production-load/camera-capacity claim. |
| AT-09 restart/replay | PASS actual HTTP process restart and deterministic stable events. |
| AT-10 query edit | PASS old observations/events retain their original immutable version; new version begins new confirmations. |

## Remaining decisions and stop

Recommendation: **CONDITIONAL GO** for Phase 2 review/testing. The software capability is ready;
AT-01 real-model camera accuracy and AT-02 RTSP hardware are not falsely marked validated.
No Phase 3 implementation, alert delivery, installer, GPU runtime, remote worker transport or
application licence selection. Real injected inference retains a soft deadline. Replay is O(n)
per query for sparse prototype histories; high-volume workloads need incremental snapshots.
Evidence deletion cannot retract exported/user-held copies or independently managed backups.
The one-operator/one-viewer key scheme is not a production account/SSO deployment. No workplace
or certified safety/accuracy claim is made. Stop for PR review and explicit next-phase authorisation.
