# Phase 5 browser session recovery — 28 October 2026

## Findings and changes

The dashboard used a one-hour signed browser session. Hidden tabs stop polling, so an
idle tab could lose its session. Repeated background requests after expiry each wrote an
authentication audit row; Trends reloaded without checking authentication. Live read-only
JSON checks found the server ready and monitoring active; this does not prove the cause
of every reported hang. Existing full-history temporal replay remains a performance limit.

Browser sign-in now lasts up to 14 days since the last authenticated request. HttpOnly,
SameSite=Strict, CSRF, role checks, loopback host restrictions and explicit logout remain.
A shared same-origin fetch guard stops further background network requests on HTTP 401,
adds recovery instructions, and prevents stale form submissions. It preserves the page and
unsaved edits. Open Start VOP to sign in again, then reload that page. Trends checks the
protected health endpoint before reloading. Denial audits are coalesced per category for
60 seconds; this deliberately sacrifices individual repeated-denial counts to bound writes.

The installed python-kasa 0.12.0 KLAP transport invalidates its session on HTTP 403 and
SmartProtocol already performs bounded handshake retries. No outer physical-action replay
was added. Unconfirmed Tapo results now include safe remediation instructions in Activity.
Successful flash sequences no longer send an unnecessary extra final off command.
Library console errors are retained, so transient 403 messages can still appear.

Changed code: browser_auth.py, service.py, dashboard.py, actions.py; regression tests cover
cookie age, logout/CSRF, audit coalescing, script ordering, stopped polling, preserved edits,
Trends authentication and flash command sequence. README, actions runbook, changelog and
package version updated to 0.6.3. No database migration or protected-setting changes.

## Validation

- `.venv\Scripts\python.exe -m pytest -q`: initial full run **447 passed, 4 skipped,
  5 failed** in 288.73 seconds. All five failures were the old per-request audit-count
  assertions; the expected count was updated for the documented denial coalescing.
- `.venv\Scripts\python.exe -m pytest tests/test_browser_session_guard.py tests/test_phase2_browser_storage.py tests/test_trends_refresh.py tests/test_actions.py tests/test_phase1_service.py -q`:
  final focused run **61 passed** in 33.87 seconds, including all five corrected cases,
  the new Tapo failure contract, and the shared JavaScript guard executed with Node.
- `.venv\Scripts\python.exe -m pip install --no-deps -e .`: installed **VOP 0.6.3**.
- `git diff --check`: passed. Git's Windows line-ending notices are informational.

The four Windows skips in the full run are Linux-only offline remote-helper cases, not
hardware tests. Full Windows and Ubuntu CI results will be recorded on the pull request
after push; they are not presumed by this report.

Managed local restart returned HTTP **202**, then a new **ready** instance. Observation
count advanced **34666 → 34672** while existing monitoring completed work and resumed.
Only protected JSON health/source metadata was read; no live page or image was inspected.

No real light/hub commands, microphone/audio, email/SMS, camera probes or model benchmark
were run for this change. No model revision or measurement is claimed. Existing authorized
monitoring may continue independently. Phase 5 hardware acceptance remains manual; Phase 6
is not started. Recommended next step: verify an unattended browser session and Activity on
the owner's normal setup, then complete remaining Phase 5 device acceptance.
