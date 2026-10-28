# Phase 5 — Record and import action audio

Date: 28 October 2026, Europe/London. Scope: requested microphone recording in
Actions → Add action → Play audio, plus the owner's follow-up about WAV usability.
Version: VOP 0.6.1. Existing Phase 5 authorisation; no Phase 6 work.

## Changes

- `src/vop/audio_recording.py`: native recording/file-import controls and a small,
  self-hosted browser script. No microphone request on load. Start/stop/cancel, native
  playback preview, discard, elapsed H:M:S, automatic 00:01:00 stop and microphone cleanup.
  Pending permission, navigation, hidden-tab and recorder-error paths release capture.
- MP3/M4A/WAV and other browser-decodable audio inputs, up to 10 MB/00:01:00. Metadata
  is checked before full decoding to avoid expanding an accidentally selected long song.
  Browser-generated recordings bypass the uploaded-file metadata probe, because WebM
  recordings may lack seekable duration metadata; their capture is time/size bounded.
- All new clips convert locally to 16 kHz, mono, 16-bit PCM WAV. The existing authenticated
  Save action route, server WAV validation, digest pinning, persistence and Windows playback
  remain the common path. No FFmpeg, new codec package, new audio service or database migration.
- No audio reaches VOP before Save action. Busy recording/conversion blocks submission;
  cancellation/failure preserves previous audio. Discard explicitly clears the unsaved clip.
- `src/vop/actions_ui.py`: load the editor only for Play audio, move old WAV-only FileReader
  logic out of shared action playback code, serve `/ui/audio-editor.js`.
- `src/vop/actions.py`: clearer missing-audio remediation. Internal WAV validation unchanged.
- `src/vop/browser_auth.py`: authenticated script access and `media-src 'self' blob:` for
  local preview only. Script/connect/image restrictions remain unchanged; operator controls,
  View/Configure separation, CSRF, 4 MB form limit and stored audio permissions are preserved.
- `src/vop/dashboard.py`: compact, wrapping controls and responsive native player width.
- `tests/test_audio_recording.py`: simulated browser/device/codec tests and real save-path
  validation. No microphone activation or audible playback.
- `pyproject.toml`, `README.md`, `CHANGELOG.md`, `docs/actions.md`: 0.6.1 and setup/limits.

## Commands and results (Windows Python 3.11)

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_audio_recording.py tests/test_actions.py tests/test_action_browser.py`
  — **25 passed in 10.35s**.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_audio_recording.py`
  — **6 passed in 3.97s**, including final size and cancellation checks.
- `.\.venv\Scripts\python.exe -m pytest -q`
  — **440 passed, 4 skipped in 247.14s**.
- `.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`
  — VOP **0.6.1** installed successfully, no new runtime dependency.
- `.\.venv\Scripts\python.exe -m pip check` — no broken requirements.
- `.\.venv\Scripts\python.exe tools/restart_smoke.py` — PASS: fresh interpreter, old
  instance replacement, retained key and three synthetic observations, loopback only.
- `.\.venv\Scripts\python.exe tools/build_release.py` — PASS: 0.6.1 wheel/portable ZIP.
- `git diff --check` — passed; ordinary Windows line-ending notices only.

Tests cover explicit-start gating, permission rejection, late permission after cancellation,
microphone release, page exit, hidden-tab stop, automatic limit, decode failure, previous-audio
preservation, oversize/long imports, discard, unsupported recording APIs, audio-only markup,
local CSP preview and use of the existing protected save route. A synthetic one-second clip
was parsed with Python's wave reader and persisted byte-for-byte; it has one channel,
16-bit samples and 16,000 frames at 16 kHz. Synthetic automatic-limit output is bounded to
60 seconds and 1,920,044 bytes. These are fixture checks, not actual recording measurements.

Final Windows/Ubuntu push/PR CI results are recorded on the pull request after push; they
are not presumed by this local report.

## Activation

Managed protected-bearer JSON `POST /ui/restart` returned **202**. A fresh instance was ready,
all **three** `(enabled, retain_evidence, sample_interval_seconds)` tuples were unchanged,
and Actions health reported no error. Observations **20590 → 20595** as previously enabled
monitoring finished/resumed. No camera frame or live page was inspected for this task.

## Limits and manual acceptance

- No actual microphone, voice recording, audible playback or real MP3/M4A codec acceptance
  test was performed. Tests substitute browser/device/decoder APIs. No new model weights,
  CUDA benchmark, manual camera capture, Tapo command or message was requested. Historical
  d1-3B revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`; no new measurements.
- Microphone support/permission depends on the browser and secure context. Loopback localhost
  qualifies; an embedded browser can still deny capture. Use current Edge/Chrome or import a file.
- Codec support varies. Uploads with unreadable/nonfinite duration, unsupported codecs,
  duration over 00:01:00 or size over 10 MB are rejected with remediation. JavaScript is required.
- Conversion intentionally targets speech/notification quality (mono 16 kHz), not music
  editing. Existing stored WAV clips are left unchanged unless a replacement is saved.
- Browser permission dialogs cannot be forcibly dismissed by VOP. Cancel restores the editor;
  if permission arrives later, its tracks are immediately stopped and recording does not begin.
- No live-browser visual QA or real microphone request was made. Prior restricted live-browser
  access was not retried. Native markup, fake-browser tests and synthetic server tests were used.

Recommendation: remain within Phase 5. Record a short clip in the owner's browser, preview it,
save, test playback and verify persistence after restart; then try a known MP3/M4A clip. There
is no automatic action execution or merge as part of this change.
