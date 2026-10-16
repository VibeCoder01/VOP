# Specification change log

## Automatic Trends refresh — 16 October 2026

- Refresh Trends every 10 seconds, retaining the current query/filter URL. Pause while the
  tab is hidden, filters have focus or filter edits have not been applied. Keep a manual
  Refresh now link and no-JavaScript guidance. Do not start sampling or inference from refresh.

## Title version and camera names in observations — 16 October 2026

- Show the installed VOP package version in small text beside VOP at the far left and in tab titles.
- Show camera/input names in individual observations, recent observations, episodes, capture
  results, Trends and inspection. Fall back to the stable source ID when no name is available.

## Observation page names and recorded-image guidance — 16 October 2026

- Rename the navigation/pages to Individual Observations and Continuous Observations
  (Episodes), retaining existing URLs and stored records. Explain that episodes group sampled
  checks and are not continuous video.
- Show whether an image is saved on each observation, with a link to its recorded image.
  Distinguish capture failure, missing images and operator-only image access.
- Show the current image-saving setting and a direct edit link on camera and observation
  pages. Explain the off-by-default policy, temporary previews, future-only changes and
  independent deletion/retention of images. Do not change any user's image-saving setting.

## Full launcher restart and browser restart — 15 October 2026

- Correct the Windows vault location so direct and packaged-Codex launches share protected
  settings. Recover missing values from legacy AppData/LocalCache without deleting originals
  or replacing shared-vault values. Preserve readable camera fields when another field fails.
- Fix Linux restart waiting on already-exited zombie processes; add a regression check.

- Make Start VOP stop existing owned servers on its port, close their worker sessions and
  launch a fresh server. Bound stale-process cleanup to the same installation, Python runtime,
  account and port; exclude the current launcher and its ancestors.
- Add operator-only Restart VOP controls in the sidebar and Settings, with CSRF/origin checks
  and automatic browser reconnection. Reload the interpreter and retain the access key.
- Stop new sampling, drain existing HTTP/background work, close the owned worker session,
  then restart. Retain persisted monitoring settings and resume them on startup.
- Add offline lifecycle regression tests and a real-loopback disposable restart smoke check.

## Metric explanations and camera names — 15 October 2026

- Add native hover explanations and accessible labels to measurement terms, overview counts
  and condition states. Describe coverage, occupancy, dwell and episode estimates from the
  existing measurement rules; no measurement calculations change.
- Name cameras at creation and rename network/USB cameras independently of credentials,
  IDs, questions and history. Persist names across restart. Read the Tapo model from its saved
  profile so a custom name cannot change which model appears in the connection editor.
- Show camera names alongside IDs in input filters and latest answers.

## Ordinal answer labels — 15 October 2026

- Show configured ordinal level names in capture results, latest answers, recent observations,
  the observation list and inspection. Keep historical labels tied to their question version.
- Describe fractional scores as between adjacent levels, without rounding an expected score
  into a category. Preserve stored numeric results, provider fields and trend calculations.
- Show the numeric score alongside the level description in all answer views.

## Visible removal and confirmed data deletion — 15 October 2026

- Put camera removal on camera rows and detail pages, with restore on the camera listing.
- Add confirmed engine-profile deletion; the selected engine must be changed first.
- Add Observations navigation, paging and capture/input-history deletion previews. Delete
  shared answers, raw runs and evidence together; pause affected rules, remove related alerts
  and deliveries, and rebuild derived history. Retain explicit timestamp-only Unknown gaps
  for individual capture deletion; complete input-history deletion also removes these markers.
- Require operator permission, CSRF, stable preview and capture/rule locks. No data is deleted
  automatically; setup, protected keys, audit records, backups and sent messages remain.

## Capture failure display — 15 October 2026

- Fix the observation page crashing when camera acquisition fails and inference time is null.
- Show that inference did not run, retain Unknown/error data and offer camera recovery guidance.
- Cover camera timeout and camera-open failure through the real pipeline and browser route
  using offline failure fixtures; retain numeric timing for actual inference attempts.

## Separate camera and engine workspaces — 15 October 2026

- Separate Cameras and Engines lists, detail pages and editors; Observe runs observations.
- Save named engine profiles independently from selecting one. Editing a profile or its key
  leaves the active engine unchanged until Use engine. Preserve camera setup on engine changes.
- Separate camera save, connection test and observation. Retain protected credentials and
  legacy integration routes; saving a camera does not connect or enable monitoring.
- Replace layered colour overrides with a restrained light interface, clear navigation,
  readable controls, concise instructions, accessible focus and reduced-motion support.

## Protected-settings diagnostics — 15 October 2026
- Distinguish an invalid camera address from unavailable protected credentials.
- Bind Windows DPAPI ctypes signatures once for concurrent readers and log failure categories
  and Windows error numbers without secret values or references.
- Add network-free camera setup readiness to authenticated JSON health. The recurring reboot
  discrepancy is not yet proven resolved; existing saved values remain intact.

## Phase 4 automatic operator workflow — 15 October 2026

- Desktop launch opens a signed-in workspace using authenticated, single-use, expiring tickets;
  long-lived keys stay internal. Manual key entry/display remains advanced.
- Observe now checks/reconnects Antec, recovers the existing worker key over trusted SSH and
  starts/reuses a bounded session, with restoration of the prior workload. Owner authorised
  automatic temporary GPU priority; no persistent service or Phase 5 deployment was added.
- Camera save/check/enable is one action; camera/question IDs can be generated. Normal setup
  reuses saved choices, with advanced configuration collapsed and plain-language retry guidance.

## Phase 4 practical-use follow-up — 14 October 2026

- Question forms now show only criteria and mock-preset guidance for the selected answer kind.
  Hidden controls are disabled and ignored by server validation for other kinds. Added visible
  Question ID syntax, browser pattern checks and duplicate/reserved-ID protection.
- Fixed sidebar button text/background contrast and made intentional chart breaks visible
  with amber unobserved-interval shading, a legend and timestamp tooltips.
- Removed extra permission checkboxes from session start, camera preview and worker selection.
  Labelled operator actions now supply permission; the launcher reuses the selected worker.
- Added linked prerequisite warnings and disabled actions for known missing setup, plus worker
  preflight before one-shot camera acquisition. Added app-wide semantic status/action colours.
- Added confirmed, recoverable removal of sources and questions, persistent across restart,
  with disabled Restore controls. Immutable history remains; dependent rules are disabled and
  queued webhook retries cancelled. Empty configurations export and reload correctly.
- Added a double-click Windows launcher with browser opening and a DPAPI-protected reusable
  operator key. Existing manual launcher behaviour remains available.
- Added explicitly authorised, bounded antec session controls with an SSH tunnel and restoration
  of the previous llama workload, plus a separate current-worker image permission form.
- Replaced raw-first health and capture pages with readable status/answers, repeat capture and
  expandable native details. These remain Phase 4 pilot conveniences, without unattended deployment.

## Phase 4 browser error follow-up — 14 October 2026

- Fixed protected camera forms reopening with a hardcoded example endpoint. Saved camera
  selection, address, username and model now reload, with separate edit/add links and blank
  password fields. Added two-camera save/reopen/restart regression coverage.

- Browser capture/setup errors now render readable guidance while API clients retain their
  JSON errors and HTTP status codes. Added a regression check for an occupied capture slot.

## Phase 4 GPU worker and live-camera integration — 13 October 2026

- Added an authenticated loopback worker with process-isolated hard deadlines, bounded admission,
  request identities/cache, explicit remote consent and validated source/model/query provenance.
- Added native backend selection/health and protected Tapo C200/C210/C510W credential setup,
  local one-shot connection tests and registration of the requested human-presence query.
- Added Windows DPAPI and Linux OS Secret Service references; no camera credentials in SQLite,
  exported configuration, worker requests or native diagnostics.
- Verified real pinned d1-3B on antec RTX 5060 Ti in BF16, and a laptop-to-antec GPU request through
  SSH plus application auth. Existing llama service restored after authorised test windows.
- Preserved CPU FP32 configuration and offline mocks; no unverified AMD/Vulkan/GPU pooling path
  or automatic fallback. Actual camera/accuracy gates depend on local owner provisioning.

## Phase 3 reliable development release — 13 October 2026

- Added immutable alert rule revisions, duration/count/health transitions, stable keys, durable
  dashboard delivery, audited acknowledgement/resolution/notes and explicit bounded HTTPS webhook retries.
- Added filtered CSV/JSON exports with provenance and formula protection; validated configuration
  import/export, SQLite-consistent backup/restore and schema-v3 migration with rollback backup.
- Added preview/apply evidence/raw-detail/audit retention, hourly opted-in policy enforcement,
  login throttling and release security/restart/recovery tests.
- Added an allow-listed wheel/ZIP Windows development installer and fresh-install smoke/runbook.
  No new camera/model/GPU test, remote inference, email delivery or licence selection is claimed.

## Phase 2 browser capability — 13 October 2026

- Added browser sessions/CSRF, operator/viewer permissions, immutable question/policy editing,
  source controls, replayed temporal states/episodes, calendar/coverage metrics and SVG trends.
- Added privacy-before-ROI preprocessing, opt-in evidence viewing/deletion, explicit bounded
  background sampling, stale/disconnect handling, schema-v2 migration/backup and browser UI.
- Preserved byte-oriented engine interchangeability and the Phase 0 model pin. No dashboard
  inference pretends to be real vision: default answers remain clearly labelled deterministic mocks.
- Authorised real USB acquisition/software checks passed without retaining pixels. No new
  real-model/GPU/RTSP test, network worker service, application licence or Phase 3 features added.

## Phase 1 foundation — 13 October 2026

- Recorded owner authorisation after Phase 0 PR #1 merge; added a Phase 1 exit contract
  traceable to the existing SRS §15 without renumbering/redesigning requirements.
- Added validated JSON configuration, explicit one-shot source adapters, mandatory
  loopback service authentication, SQLite immutable question versions/observations/audit,
  byte ingestion/idempotency, bounded admission and offline API/persistence tests.
- Reused provider-neutral inference and image validation; added a typed guard for untyped
  provider results. No dashboard, episode metrics, remote workers or Phase 2 features added.

## Phase 0 implementation — 13 October 2026

- Implemented the P0-01–P0-10 contract as a still-image CLI, byte-oriented typed contracts,
  interchangeable synthetic mock engines and an optional pinned Liquid adapter.
- Added offline tests, Windows/Linux CI, locked offline dependencies, synthetic fixture,
  guarded isolated benchmark, PowerShell runbook and feasibility/validation reports.
- Corrected the illustrative plugin starter's SRS reference from v0.1 to v0.2; no SRS
  requirements, IDs or intended plugin semantics changed.
- Application licence remains open. No Phase 1 services or remote worker networking added.

## v0.2.1 — 13 October 2026 — Inference placement clarification

- Confirmed that the SRS already mandates provider-neutral inference (INF-001) and plans remote workers (INF-011, OPS-010, NFR-017). **No SRS requirements or numbering changed.**
- Added a Phase 0 design-only guardrail: CPU-only Dell benchmark is not a local-only product decision. Camera capture, inference, storage and dashboard may reside on different machines in later deployments.
- Required a location-neutral inference contract and offline interchangeability test using two mock provider instances; no remote network service, RPC or hardware requirement added to Phase 0.
- Documented model placement, payload portability, explicit engine routing and safe future fallback behaviour in ADR-0002.

## v0.2 — 13 October 2026 — Final Codex handoff review

- Preserved existing requirement IDs and modular system architecture.
- Added a controlling, executable **Phase 0** scope and acceptance matrix in `CODEX_PHASE_0.md`.
- Added concise repository instructions (`AGENTS.md`) and a ready-to-paste Codex task (`CODEX_START_PROMPT.md`).
- Resolved scope drift: no UI, database, RTSP, live camera or full MVP delivery in Phase 0; offline/mock vertical slice first.
- Required explicit real-model opt-in and accurate recording of memory/latency, model revision, errors and non-execution.
- Clarified that `noul`, `choice` and `score` are provider responses; durations, frequencies, rates and event episodes are later derived measurements, not model-native numeric outputs.
- Added a model/runtime trust and licensing review gate. Liquid's LFM Open License v1.0 is **not** necessarily equivalent to an OSI-approved software licence; evaluate applicable usage and redistribution conditions independently.
- Clarified that CPU feasibility failure is a valid Phase 0 finding, not permission to report success or skip acceptance evidence.
- Added safety note about missing frames, preflight resource checks, local/private test images and offline CI.

## v0.1 — 13 October 2026 — Initial requirements baseline

- Product vision, architectural boundaries, detailed requirements, data model, plugin contracts, acceptance scenarios and roadmap.
