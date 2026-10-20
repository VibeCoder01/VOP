# Continuous monitoring status and camera turns — 20 October 2026

Show Monitoring is running for the complete per-camera monitoring session, including
between samples and while another camera is processed. Genuine missing setup requirements
remain separate warnings and do not hide the monitoring session status. Synthetic engines
remain labelled as synthetic.

The existing sampler already processed sources sequentially. Make turn-taking explicitly
round-robin: start scanning after the last attempted input, process one due source per tick,
and yield to the next input. Preserve independent intervals, failure backoff and the single
in-flight frame contract. Missed intervals never create a backlog of old images.

Observe now captures immediately when free. When busy (or already pending), keep one manual
intent per camera under a lock and process a fresh frame on its round-robin turn. Duplicate
clicks coalesce. A pending manual request works even when repeated monitoring is paused and
does not enable repeated monitoring. Show an acknowledgement and link to Individual
Observations; show pending status on Observe. This is an intent queue, not an image queue.

Start/Pause bypass capture HTTP admission after authentication, role, origin and CSRF checks.
A manual-capture POST that finds admission occupied can only schedule its intent; it cannot
release another request's lock. The first capture retains admission normally. Pipeline
locking continues to enforce one in-flight capture, and API overload behavior is unchanged.

Changed files: `src/vop/dashboard.py`, `src/vop/browser_auth.py`, `src/vop/sampling.py`,
`tests/test_operator_workflow.py`, `tests/test_phase2_sampling_roi.py`, `README.md`,
`CHANGELOG.md` and this report. This refines the authorised Phase 4 pilot.

Windows commands/results:

- `.\.venv\Scripts\python.exe -m pytest tests/test_operator_workflow.py tests/test_phase2_sampling_roi.py tests/test_ui_modes.py -q`:
  28 passed in 12.41 s. Covers stable status between samples and while busy; round-robin turns
  across three synthetic sources; paused sources; no obsolete catch-up frames; failure
  backoff; coalesced manual requests; fresh capture after contention; and no accidental
  enabling of repeated monitoring.
- `.\.venv\Scripts\python.exe -m pytest -q`: 312 passed, 4 skipped in 63.56 s. The skips
  are Linux-only helpers. This full run preceded the final HTTP-admission refinement.
- `.\.venv\Scripts\python.exe -m pytest tests/test_operator_workflow.py tests/test_phase2_sampling_roi.py tests/test_ui_modes.py tests/test_lifecycle.py -q`:
  35 passed in 10.77 s after final refinement. A held manual capture allows a second input's
  Start/Pause and repeated Observe now clicks; exactly one pending observation is later
  processed. Tests use synthetic inputs/mock engines with the background sampler stopped.
- `git diff --check`: passed.

Applied using the authenticated dashboard restart endpoint. A new process returned healthy,
with all source enabled/image-saving/interval controls preserved. Existing monitoring drained
and resumed; observation count increased from 1600 to 1602. No new manual multi-camera,
Antec, real-model or GPU test was performed and no new hardware benchmark is claimed.
No dependencies, schema or model revision changed. Historical approved d1 revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Limits: one frame is processed at a time, so multiple cameras share throughput. Intervals
are targets, not a guaranteed frequency under load. An in-flight observation completes
before another takes its turn. Manual intents are per-process and are lost on restart;
removed/disabled inputs or inputs with no enabled questions discard their intent. Pause
stops repeated monitoring, not a separately requested one-shot observation. Unexpected
sampling errors remain available in health metadata. Review normal multi-camera use in
Phase 4; Phase 5 remains unauthorised.
