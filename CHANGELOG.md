# Specification change log

## 0.6.0 — Actions and Automations (27 October 2026)

- Separate Actions/Automations configuration and Activity view; native forms, named choices,
  previews, explicit tests, setup help and live delivery results.
- Durable, expiring action jobs with deduplication, cooldown, schedule, hourly limits,
  pause/restart handling and cancellation on camera/question removal or history deletion.
- Browser/Windows beep and uploaded WAV audio; optional python-kasa 0.12.0 adapter for
  L530 lights and H100 built-in sounds; SMTP SSL email and Twilio outbound SMS.
- Protected account/recipient bundles, no default destinations, no automatic effects from
  synthetic observations. Accepted delivery and uncertain outcomes are stated honestly.
- Hardware/provider acceptance remains manual and opt-in. See docs/actions.md.

## Observe image pairs — 27 October 2026

- Pair compact live/current images with the completed source frame used by the
  latest enabled answers; enlarge either on hover or keyboard focus.
- Separate completed result previews from in-flight and camera-test previews.
- Pin processed-image requests to answer frame IDs, keep image/answer updates
  matched, and show explicit missing-image states without older-frame substitution.
- Preserve masking, operator-only pixels, saved-image settings, automatic image
  hiding on pause and the independent live refresh loop.

## Episodes timeline — 26 October 2026

- Rename Continuous Observations (Episodes) to Episodes (Contiguous active observations).
- Show all-time episode counts beside camera names, retaining multiple selection.
- Add a scrollable SVG timeline with centred zoom, Fit, pinned labels/time axis,
  per-camera/question/version rows, episode links and recorded-gap distinctions.
- Limit the timeline to the latest 1,000 matching episodes and retain 100 detail rows;
  explain the scope. No inferred duration is added after the last recorded sample.

## Runtime loop efficiency review — 26 October 2026

- Reuse question, source, summary and provenance reads within one alert evaluation;
  fetch provenance only for a new alert transition. Reload on the next evaluation.
- Batch notification deliveries and per-camera native answers; aggregate saved-image
  counts in history previews instead of querying once per capture.
- Skip already-cleared raw history/images during retention and precompute export
  membership sets once.
- Index question/version history order and newest saved-image reads.
- Stream backup/restore checksums with bounded memory. Keep replay, validation,
  acquisition deadlines and worker scheduling semantics unchanged.
- Document the remaining full-history temporal replay cost and bounded cleanup waits.

## Efficient question deletion — 26 October 2026

- Add an observation lookup index by capture run, including existing databases on
  startup, to avoid repeated full-table scans during shared-answer cleanup and
  capture foreign-key checks.
- Use metadata-only question deletion previews; remove unused full-history hashing.
- Avoid rewriting already-cleared images. Preserve atomic deletion, fresh shared
  result reads, other normalized answers and the progress dialog.
- Add deterministic SQL-work scaling checks with shared and exclusive captures.

## Question deletion progress — 26 October 2026

- Show a native modal with an indeterminate progress bar after confirming single or
  bulk question deletion. Explain that large histories can take time.
- Keep native result/error navigation, prevent duplicate submits and reset the
  dialog when returning through browser Back. No invented percentage or time estimate.
- Preserve the normal form workflow when JavaScript or dialog support is unavailable.

## Delete questions during monitoring — 26 October 2026

- Bind question deletion confirmation to question/rule configuration, rather than
  changing observation counts. New observations no longer force repeated confirmation.
- Delete all matching data under the existing capture/alert locks, including data
  recorded while waiting. Preserve camera monitoring settings and other questions.
- Explain preview counts and shared-image effects; retain configuration-change,
  permission and atomic rollback protections for single and bulk deletion.

## Observe refresh and counters — 24 October 2026

- Refresh camera previews independently; one slow request no longer blocks other cameras.
- Update Active and Unknown counters with current answers, including while answers are hidden.
- Count RECOVERING episodes as active until end confirmation; keep counters scoped to selected cameras.

## One camera entry and page — 24 October 2026

- Replace Open camera/Edit settings/Remove row actions with one Manage camera button.
- Make the canonical camera page the editable form with connection status/testing,
  observations, recorded images, Questions and Remove camera in a logical order.
- Redirect old edit/rename/observation links to the same page. Save and test connection
  uses the form's current values and keeps the connection-test result flow explicit.

## Unified camera settings — 24 October 2026

- Combine camera identity/connection, enabled state, observation interval and image
  saving in one grouped editor and one Save action, for network and USB cameras.
- Replace duplicate detail-page edit/rename/observation links with Edit settings;
  redirect old observation and rename editor links to the unified form.
- Validate intervals before protected writes. Preserve observation settings for old
  connection-only clients and retain a saved password when changing the username.

## Explain advanced question settings — 24 October 2026

- Add linked help for Yes/No threshold, positive/negative confirmations, all gap
  policies, maximum observation gap, ROI and question enabled status.
- Link question observation help to the camera interval form and explain the target
  per-camera interval, shared by its enabled questions, including pauses and delays.
- Explain the current hold-for-review limitation without promising an approval action.

## Trends camera buttons — 24 October 2026

- Replace Trends source/timezone dropdowns with multi-select camera-name buttons.
  Use workspace timezone and retain date filters and automatic refresh.
- Preserve applied dates on camera toggles/reset and all selected cameras on Apply
  dates. Replay summaries only for selected cameras.

## Observation history camera buttons — 24 October 2026

- Use multi-select camera-name buttons on Individual and Continuous Observations,
  sharing the existing Observe selection pattern and All cameras reset.
- Filter in SQL before the global result limit; keep combined results newest first
  and retain every selected camera on Older answers links.
- Remove the Continuous Observations timezone control and use workspace timezone.
  Keep retired cameras out of buttons and preserve individual-history deep links.

## Isolate Questions configuration from history counts — 24 October 2026

- Render configuration/edit/delete controls before querying history. Load count cells
  separately in a worker thread, with failure/retry handling and no row replacement.
- Replace the count query's repeated temporary-table scans with one grouped pass.
- Add metadata indexes for observation counts and saved-image presence, avoiding
  lookups through tables containing answer/image payloads. No count cache is added.
- Verify bounded SQL work and responsive configuration/health during stalled counts.

## Direct question deletion and faster Questions page — 23 October 2026

- Replace recoverable question removal with direct confirmed Delete question and data.
  Include existing removed questions in the same list, retain bulk deletion and remove
  question Restore controls. Old links open confirmation without deleting anything.
- Use count-only aggregate queries for Removed questions instead of building a full
  deletion preview for every row. Do not load result payloads or query per capture.
- Reuse aggregate counts in deletion previews while preserving detailed fingerprints,
  stale-data confirmation and transactional deletion guards.

## Queued removal and simpler camera controls — 23 October 2026

- Wait for current observation/alert work when removing or restoring questions/cameras.
  Recheck the item after waiting and keep the dashboard responsive.
- Replace Observe source/timezone filters with multi-select camera-name buttons.
  Apply selection to camera cards and summary totals, and preserve it on refresh.
- Make Camera setup Edit a button matching Open camera/Remove; reduce row padding.

## Wait for question deletion — 23 October 2026

- Single and bulk permanent question deletion wait for request admission, the current
  observation and alert processing instead of returning a busy error.
- Keep the dashboard responsive while waiting and recheck the complete selection and
  recorded-data fingerprint before any deletion. Changed data requires confirmation again.

## Questions selectors and bulk removed-question deletion — 23 October 2026

- Replace Questions source/timezone filters with camera-name selector buttons.
- Show compact Removed questions rows with camera names and all-version data counts.
- Add checkbox multi-selection and a shared confirmation for permanent bulk deletion.
- Always purge recorded data when permanently deleting a question. Validate the whole
  batch before committing; preserve unselected normalised answers and prevent deleted
  answers from reappearing through another selected question's shared result.

## Compact Observe controls and steady Trends — 23 October 2026

- Group the sidebar current-mode indicator and existing mode switch.
- Disable the four-pixel workspace entrance movement on Trends, including automatic refresh.
- Align monitoring and Show/Hide answers controls, with full-width answer content below.
- Label live answer state as Episode State, remove the ordinal Expected level prefix,
  and reduce answer cell/bar spacing while retaining labels, numbers and tooltips.

## Observe image visibility — 22 October 2026

- Add an independent Show image / Hide image disclosure per camera.
- Show images when monitoring starts; hide them when it pauses. Respect manual
  visibility choices until monitoring changes or the page reloads.
- Stop image downloads and preview lease renewal while hidden; keep status checks
  and existing answer updates. A hide during decoding does not reopen the image.

## Save cameras while monitoring — 22 October 2026

- Wait automatically for an active observation or configuration request when adding
  or editing a camera, instead of rejecting the form as overloaded.
- Defer protected address/account writes until the observation finishes, keeping the
  saved source and connection details consistent while the request waits.
- Keep the UI responsive and monitoring enabled; retain existing scheduled connection
  tests and machine API overload behavior.

## Live answer panels and value bars — 22 October 2026

- Refresh open Observe answer panels every 0.2 seconds without reloading the page or
  replacing camera images. Pause requests for closed panels and hidden tabs.
- Use conditional responses to skip unchanged tables and full-history replays; refresh
  state when answers expire, settings change or recorded data is deleted.
- Add labelled Yes/No, ordinal and choice value bars with native score semantics,
  numeric values and tooltips. Missing/stale results do not become zero values.

## Observe refresh and engine result layout — 22 October 2026

- Allow same-origin background requests in the browser security policy so live preview
  leases and image checks can run. Keep other origins blocked.
- Decode replacement images before swapping them into Observe, preserve the displayed
  image on failed loads, and retry without reloading the page or closing answer panels.
- Group Check again and Back to Engines as spaced, consistently styled buttons.

## Near-real-time Observe previews — 22 October 2026

- Separate visible-page RTSP/USB previews from model sampling, using persistent
  supervised decoders and latest-frame replacement instead of repeated reconnects.
- Target 5 fps with masked 960 × 540 JPEG frames and 0.2-second browser checks;
  pause hidden-page renewal and close idle connections after 15 seconds.
- Keep preview frames memory-only and operator-protected. Reconnect stalled cameras,
  bound the active decoder count, and release exclusive USB devices for observations.
- Add an offline synthetic process smoke check to Windows/Linux CI and the release.

## Per-camera answers on Observe — 22 October 2026

- Move the shared Latest answers table into each camera’s Observe section.
- Add independent Show answers / Hide answers controls, initially collapsed, using
  native browser disclosures. Preserve states, question versions, values and times.

## Observe images and camera-test layout — 22 October 2026

- Show the latest masked image per camera on Observe, with green monitoring and
  amber paused rings, timestamps and automatic refresh without additional captures.
- Keep one temporary preview per configured camera; use clearly labelled retained
  images after restart where available. Preserve operator access and evidence settings.
- Keep camera-test buttons together below the picture and clear each camera’s
  cached image when its recorded data is deleted.

## Settings tabs and live workspace cleanup — 21 October 2026

- Split Settings into Notifications, Rules, Export, Configuration and backup, Retention
  and Audit tabs. Use named selections, native date pickers and automatic rule IDs.
- Fix shared filter-field margins and align new form controls in a responsive grid.
- Remove the MOCK alerts banner. Live launches remove stored test equipment and
  records, preserve real data and settings, and prevent test configuration from
  returning after restart. Offline test fixtures remain available and labelled.

## Clearer measurements and queued camera tests — 21 October 2026

- Remove daily-count/choice-dwell panel; label Yes/No questions plainly.
- Format durations as H:M:S with one decimal second, and rates, percentages and
  numeric answers to one decimal without changing stored measurements.
- Explain Observation coverage and Condition active, including the meaning of higher values.
- Queue busy camera tests for the next free slot, before periodic observations;
  update their result page automatically without inference or retained evidence.

## Optional recorded-data deletion with a removed question — 21 October 2026

- Add an unchecked recorded-data deletion option and counts to the question confirmation.
  Recheck counts on POST and delete data atomically with configuration deletion.
- Purge all versions’ answers, gaps, associated images, episodes, alerts and delivery records.
  Preserve other normalised answers, remove shared opaque raw payloads and clearly show the
  shared-image impact. Keep default history retention, audit and historical definitions.

## Setup-only Configure navigation and deleted questions — 21 October 2026

- Show only Cameras, Engines, Questions and Settings in Configure navigation. Remove its
  viewing shortcuts; keep recorded-data administration under Settings → Manage saved data.
- Add a confirmed Delete permanently option for removed questions. Keep historical answers,
  versions, images, episodes and disabled rules; prevent app restoration or seed-config
  resurrection. Reserve historical IDs and generate unused IDs for replacement questions.

## Simpler Observe and mode navigation — 20 October 2026

- Hide Observe now while that camera is monitoring. Remove the recent-observation table
  from Observe; use Individual Observations for recorded checks.
- Rename Removed cameras to Retired Cameras and omit retired inputs from the Individual
  Observations filter without deleting history. Restored cameras return to the filter.
- Use one consistent sidebar mode toggle. Omit Observe navigation and shortcuts in Configure
  mode, with Cameras as its landing page. Keep setup prompts on the same sidebar switch.

## Deterministic history-deletion tests — 20 October 2026

- Stop unrelated background workers in deletion tests. Preserve explicit busy-lock tests
  and production guards. Fix an intermittent Windows CI 429 during history deletion.

## Remove internal worker activity from Observe — 20 October 2026

- Remove the shared-worker activity panel. Keep camera monitoring status, scheduled
  observation acknowledgements and actionable setup warnings. Scheduling is unchanged.

## Continuous session status and camera turns — 20 October 2026

- Keep Monitoring is running visible between samples and during other camera turns.
- Schedule due cameras round-robin, one fresh frame per turn, retaining intervals and
  failure backoff. Permit Start/Pause monitoring while a manual capture occupies HTTP
  admission; retain CSRF, viewer permissions and single-frame pipeline locking.
- Keep Observe now available during automatic monitoring. Schedule one fresh observation
  per camera when busy; combine repeated clicks without queuing images or enabling monitoring.

## Normal monitoring activity status — 20 October 2026

- Show an active observation as neutral Observing status, rather than a setup failure.
  Disable manual capture while busy, keep Pause monitoring available, and preserve real
  dependency warnings. A stale manual capture reports that no extra observation was started.

## Monitoring controls in View mode — 20 October 2026

- Restore Start/Pause monitoring on Observe in View mode for operators, including starting
  a paused input. Keep setup and interval editing in Configure mode. Preserve viewer and
  CSRF restrictions, saved sampling intervals and worker-session cleanup on pause.

## View and Configure modes — 20 October 2026

- Default to View mode on sign-in. Put setup, monitoring controls, deletion and restart in
  Configure mode with an explicit sidebar switch. Keep enabled-input observations and
  permitted saved images available in View mode; preserve running monitoring and saved setup.
- Enforce browser mode on direct setup routes and writes. Keep viewer restrictions, CSRF
  and existing bearer API permissions. No additional key or account is needed.

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
