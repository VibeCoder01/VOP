# Phase 5 — Actions and Automations implementation

Date: 27 October 2026 (Europe/London). Authorisation: accepted Actions plan, followed by
“Please proceed with implementation”; subsequent owner addition: H100 hub sound. First
light target supplied by owner: L530. No Phase 6 work or automatic merge is authorised.

## Delivered behaviour

- Configure: distinct Actions and Automations pages, named choices, relevant action/trigger
  fields, protected setup, editing, confirmed deletion, previews and explicit real-action tests.
- View: Activity, with incremental one-second result refresh, global automation pause and
  actionable setup links. Operator sound control is available in both modes.
- Named browser/Windows beep and uploaded PCM WAV actions; optional L530 on/off/flash,
  brightness/colour and H100 built-in sound/volume/duration through python-kasa 0.12.0.
  Check device reads information only and loads the H100's actual sound options.
- SMTP SSL email and Twilio HTTPS SMS adapters using the standard library. Protected
  accounts and recipients stay outside SQLite/configuration exports. Text templates have
  four literal substitutions and do not execute expressions or attach camera images.
- Confirmed episode start, observed duration, confirmed end, named answer changes and
  observation unavailable/recovered triggers. Ordinal thresholds compare the numeric
  position against a named level. UNKNOWN does not mean safe, closed or a matching answer.
- Persistent deduplicated queue, two-minute expiry, cooldown, daily schedule, hourly limits,
  explicit pause and restart baselines. Provider acceptance is distinguished from final
  delivery. Ambiguous effects are not automatically retried. Only definite SMS rate-limit
  rejection is retried. Startup does not replay waiting or historical actions.
- Queue execution is separate from camera capture/inference. Browser claims are single-use
  across tabs. Audio is pinned by digest so editing a WAV cannot replace a claimed job's file.
  Idle evaluation avoids writer transactions and caches temporal replay until data/policy
  changes; staleness ages independently. Repeated triggers use indexed exact-key lookups.
- Camera retirement/question deletion cancels jobs and pauses associated automations;
  deleting related history erases associated activity. Synthetic/mixed-provenance episodes
  cannot cause automatic physical/messaging actions. Manual tests are deliberate exceptions.
- Additive Actions storage extension version 1 within existing schema-3 SQLite. Full backup
  preserves definitions, queue and WAV bytes. Legacy configuration JSON remains importable;
  JSON containing Actions directs users to full backup/restore instead of silently losing data.

## Changed files

| Files | Purpose |
|---|---|
| `src/vop/actions.py` | Validation, persistence, transition evaluation, queue, adapters, lifecycle and deletion hooks |
| `src/vop/actions_ui.py` | Forms, setup help, simulation preview, Activity fragments and targeted audio/upload JavaScript |
| `src/vop/service.py`, `dashboard.py`, `browser_auth.py` | Service lifecycle/health, navigation/sound control, operator/mode/CSRF/body/CSP integration |
| `src/vop/history_deletion.py`, `removal.py` | Cancel/erase related action data without reintroducing deleted questions |
| `src/vop/reliable.py`, `release_ui.py` | Redacted definition export and clear distinction between existing notification rules and automations |
| `tools/release.py`, `tools/build_release.py` | Honest JSON import boundary and packaged Phase 5 setup documentation |
| `tests/test_actions.py`, `test_action_browser.py` | Offline acceptance using intercepted device/message/audio delivery and a fake browser |
| `tests/test_ui_modes.py`, `test_phase1_service.py`, `test_phase2_browser_storage.py` | Updated navigation and self-hosted asset expectations |
| `pyproject.toml`, `AGENTS.md`, `CODEX_PHASE_5_PLAN.md`, `docs/actions.md`, `README.md`, `CHANGELOG.md` | Version 0.6.0, optional pinned Tapo adapter, authorisation, runbook and limitations |

## Local validation

Commands used the repository's Windows Python 3.11 virtual environment:

- `.\.venv\Scripts\python.exe -m pip install python-kasa==0.12.0` — successful installation.
  Inspected installed Discover, Light and Alarm signatures; **no discovery or device command**
  was made for this check. Optional adapter is excluded from default offline dependencies.
- `.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .` — VOP 0.6.0 installed.
- `.\.venv\Scripts\python.exe -m pip check` — no broken requirements.
- `.\.venv\Scripts\python.exe -m pytest -q` — **432 passed, 4 skipped in 236.19s**, before
  the final audio-digest/backup and remediation refinements. The earlier full run was
  430 passed, 4 skipped; old script-count and JSON import expectations were corrected.
- Final focused `.\.venv\Scripts\python.exe -m pytest -q tests/test_actions.py tests/test_action_browser.py tests/test_settings_tabs.py`
  — **22 passed in 11.09s**. Covers the final refinements, permissions, browser disable/claim
  race, audio replacement, full backup and JSON import boundary. Current collection: 438 tests,
  including the four opt-in hardware tests. Final complete Windows/Ubuntu CI results will be
  recorded on the pull request after push; this report does not presume CI success.
- `.\.venv\Scripts\python.exe tools/phase1_smoke.py` — PASS: HTTP capture 201, duplicate 200,
  unauthenticated 401, six observations persisted across process restart.
- `.\.venv\Scripts\python.exe tools/phase2_smoke.py` — PASS: browser/CSRF, confirmed episode,
  deterministic replay, viewer evidence 403, deleted evidence 404, 21 persisted observations.
- `.\.venv\Scripts\python.exe tools/phase3_smoke.py` — PASS: alert idempotency, acknowledgement,
  CSV/JSON export, retention preview, full backup/restore with 18 observations; no outbound delivery.
- `.\.venv\Scripts\python.exe tools/phase4_smoke.py` — PASS: explicit synthetic worker over
  actual loopback HTTP, three persisted observations, disconnection UNKNOWN, actual Windows DPAPI.
- `.\.venv\Scripts\python.exe tools/preview_smoke.py` — PASS: five synthetic frames, verified
  masking, independent preview while inference slot held and producer cleanup after lease expiry.
- `.\.venv\Scripts\python.exe tools/restart_smoke.py` — PASS: fresh interpreter, stale-instance
  replacement, retained access key and three observations. Loopback; no real camera/model.
- `.\.venv\Scripts\python.exe tools/build_release.py` — PASS: `dist/vop-0.6.0-windows-dev.zip`
  and wheel, with allow-listed Phase 5 documentation. No runtime DB, credentials or images bundled.
- `git diff --check` — passed (only existing Windows line-ending conversion notices).

## Activation evidence

Protected-bearer JSON checks and managed `POST /ui/restart` only; no live HTML or image
inspection. HTTP **202**, fresh instance ready, all **three** source control tuples
`(enabled, retain_evidence, sample_interval_seconds)` unchanged, Actions health available
with no error. Observation count **18911 → 18913** as existing work finished and monitoring
resumed. No default actions or automations are created by this release. Normal previously
enabled monitoring can still use the existing engine; that is not a new model benchmark.

## Skipped hardware/provider checks and limits

- No real L530/H100 command, audible playback, email or SMS test. Offline adapters intercept
  every effect. Firmware/network/account compatibility and perceived sound require owner tests.
- No new model download, GPU run, performance measurement or manual camera request. Historical
  d1-3B revision `051bcc464b01b9f92942b364d9586b0ef5912432` remains historical evidence only.
- No live browser visual QA; native markup, fake-browser script tests and synthetic HTTP smoke
  checks were used. Previously restricted live-browser/image access was not retried.
- WAV only, maximum 2 MB/00:01:00; browser autoplay requires an enabled visible tab. Computer
  sound currently Windows only. One browser claims each sound; interrupted playback is not
  reassigned automatically. Browser permission can require another click after a reload.
- L530 flash finishes off and has bounded normal execution, but power/process/network failure
  can interrupt cleanup and leave it on. In-progress effects may finish after pause/deletion.
- SMTP SSL only; one recipient per named action. SMS uses Twilio and may incur charges.
  Provider acceptance is not a delivery receipt. No arbitrary scripts, inbound webhook or
  image attachments. Tapo support is optional, community-maintained and not hardware-verified here.
- One camera/question per automation; reuse named actions across multiple automations.
  A single delivery worker runs server actions sequentially; a long action can delay later jobs.
- Full-history temporal replay on new samples remains the existing architectural limitation;
  this feature caches unchanged summaries but does not replace measurement/replay semantics.
- Full backup/restore is required for Actions data; JSON import intentionally refuses nonempty
  Actions packages. OS-protected secrets must be supplied separately on another machine/account.

Recommendation: complete manual Phase 5 acceptance with an L530 turn-on test, a short low-volume
H100 sound, browser/Windows audio, then configured email/SMS. Review Activity and restart/pause
behaviour before enabling unattended automations. No Phase 6 implementation or merge is performed.
