# Visual Observability Platform — Actions and Automations

Phase 4 adds an authenticated process-isolated inference worker, explicit dashboard backend
selection, protected Tapo credentials and repeatable camera connection tests. Actual pinned
d1-3B CUDA/BF16 execution and a laptop→antec fixture request passed. Default inference remains
mock until deliberately changed. C200/C210 live validation needs local credential setup;
C510W was reported temporarily unavailable during that pilot. Phase 5 Actions and Automations
was authorised on 27 October 2026; see [setup and limitations](docs/actions.md).

## Everyday use on this laptop

**Diagnostics** is available in View and Configure modes. It separates monitoring settings,
scheduler progress, engine connection failures and camera failures, with last attempt/image
times, retry delays and explicit **Check and reconnect engine** / **Test camera connection**
controls. Opening the page is passive; it does not connect to cameras or start an engine.
Use Refresh diagnostics for a new snapshot. Camera tests run without inference.
Large traffic lights show green for recent success/running services, amber for paused,
waiting or unverified checks, and red for reported failures. Each light has a text label;
the top summary points out any component needing attention. They do not indicate detection accuracy.

If `antec.local` cannot resolve, the verified Antec pilot can use `antec` while still checking
the original `antec.local` SSH host key. Unknown/changed keys remain rejected. No address or
credential changes are needed for this fallback. Existing enabled monitoring resumes normally.

Ordinal answers show their configured level names. Liquid d1 returns an expected position:
for levels Low, Medium, High, a score of 0 is shown as **Low (0.0)** and 0.25 as
**Between Low and Medium (0.2)**. This is not a rounded category or a calibrated
probability. Technical details preserve the numeric score and provider probabilities.
Recorded answers use the level names from their original question version.

Double-click **Start VOP.cmd**. It opens your signed-in workspace using a short-lived, single-use
local launch link; you do not copy any keys. Keep its terminal window open while using VOP.
Start VOP now stops previous VOP servers from this installation on the same port before it
starts a fresh server. It asks responsive servers to finish their work and close their owned
worker sessions; after a bounded wait it clears stale processes and their children. Other
applications, other installations, other Windows accounts and other ports are left alone.
If another application owns the port, the launcher explains the conflict and stops.

Use **Restart VOP** in the sidebar or **Settings → Restart VOP** to restart from the browser.
The workspace reconnects automatically when JavaScript is enabled. The current observation
finishes before shutdown; background sampling stops before worker cleanup. Saved camera
details, names, questions, backend, login key and monitoring choices are retained. Monitoring
resumes when the new server starts. This restart reloads application code as well as settings.
If restart cannot complete, open **Start VOP** to clear stale instances. Advanced servers
started outside `tools/run_dashboard.py` do not expose an enabled restart control.

Saved cameras, questions and the selected backend are reused. Click **Observe now** on a
paused camera for one result. While continuous monitoring is on, only **Pause monitoring**
is shown; pause first if you want a one-shot observation.
Use **Start monitoring** for repeated observations (10 seconds by default, or your saved custom
interval) and **Pause monitoring** to stop them. Pause leaves manual observations available;
when no other scheduled source is active and no capture is in flight, it also stops the owned
Antec session and restores the previous workload. Interval and pause choices persist.
**Monitoring is running** stays visible throughout a monitoring session, including between
samples and while another camera takes its turn. Enabled cameras are sampled round-robin,
one fresh frame at a time, using their saved intervals without queuing old frames. You can
start or pause another camera while a capture runs. For cameras not continuously monitored,
**Observe now** takes an image immediately
when the worker is free; otherwise it schedules one observation for that camera’s turn.
Repeated clicks combine into one pending request per camera. Only the camera request waits;
its image is captured fresh when processed. Open Individual Observations to read its result.
Pending one-shot requests are held in memory and do not survive a VOP restart.
Observe shows camera monitoring and requested-observation status; routine internal activity is hidden.
**Needs attention** indicates a setup prerequisite such as a missing question or unavailable saved credentials; monitoring status remains visible alongside it.
For the established Antec pilot, VOP checks/reconnects the worker, recovers its existing key over
trusted SSH when needed, and starts or reuses a 15-minute GPU session automatically. The owner
authorised temporarily pausing the existing workload for these on-demand sessions; it is
restored on session end, Stop or disconnect. Configured sampling can request a new timed session
when it next needs inference. Stop sampling or close VOP when you no longer want it using the GPU.

Use **Cameras → Add camera** to save its address and camera account. Saving does not open the
camera or start observations. Open that camera, then **Test camera** to receive one preview.
Use **Observe** to run questions against it. Camera IDs are generated; new cameras start paused,
with sampling and evidence retention off. Question IDs are also generated when left blank.
Give the camera a name during setup, or open its page and choose **Rename**. Renaming also
works for USB cameras and does not require camera credentials. Names survive app restarts;
the camera ID, connection, questions and recorded history stay the same.

VOP opens in **View mode** after sign-in, including Start VOP. View mode shows Observe,
Individual Observations, Episodes (Contiguous active observations) and Trends. Operators can run
**Observe now** on an enabled camera that is not monitoring, **Start monitoring** or
**Pause monitoring**, and view
permitted saved images. Start also enables a paused input. Existing monitoring continues
when you switch modes. Choose **Configure mode** on the single sidebar mode switch to manage cameras,
engines, questions, monitoring intervals, image saving, deletion and restart. The current-mode
indicator and switch are visually grouped in one sidebar panel. Choose **View mode**
when finished. No extra access key is required. The selected mode stays in this browser
session; a fresh sign-in returns to View mode. Viewer credentials cannot enter Configure mode.
Configure mode opens Cameras and lists only Cameras, Engines, Questions and Settings;
Individual Observations, Episodes (Contiguous active observations) and Trends stay in View mode.
Saved-data deletion remains available through Settings → Manage saved data. Use the same sidebar switch to return to View mode.
Old setup links direct you to the single sidebar mode switch. A stale form submitted in View mode
is refused; switch modes and reopen the form. Authenticated bearer API clients keep their
existing permissions. Modes simplify the interface; they are not separate user accounts.

Observe omits the duplicate recent-observations table. Retired cameras are omitted from the
Individual Observations filter; their stored history remains available through All inputs
and existing history links, and restoring a camera returns it to the filter.

**Individual Observations** lists each recorded answer from a capture. **Episodes
(Contiguous active observations)** groups checks into confirmed episodes; it does not mean continuous
video recording. URLs and existing records are unchanged.
The VOP title at the far left shows the installed version in small text; browser-tab titles include it too.
Observation lists, episode lists, Trends and result pages use the camera/input name when available,
with its stable ID as the fallback. IDs remain unchanged in URLs and technical details.
Trends refreshes every 10 seconds while its tab is visible. Automatic refresh pauses while
you focus or change its filters; apply changes to resume. Selected camera, date range and time
zone stay in the page URL. Trends has no page entrance movement on refresh. Refresh
updates recorded results and does not start monitoring.
With JavaScript disabled, use **Refresh now** instead.

Images are optional and saving is **off by default**. A capture can show a temporary preview
without keeping it. On the camera page, **Recorded images → Change image-saving setting**
opens **Save images for Individual Observations**. Turn that on and save to keep one
privacy-masked still image per future capture, shared by all its answers. The observations
list shows **View saved image**, **No image saved** or **No image captured**; open an individual
observation to see its image. You can also select an input on that list to see the current
setting and its edit link. Images remain restricted to operators under the current access policy.

Turning image saving on cannot recover old unsaved or deleted images. Turning it off does
not delete images already saved. Manual deletion and retention rules can remove images while
keeping answers, so a missing historical image does not prove what the setting was at capture time.

Hover over the dotted-underlined metric labels and condition states for plain-language
explanations. These include Active conditions, Unknown conditions, Coverage, Occupancy,
Covered time, Valid samples and episode duration/gap terms. The same explanations are
included in the labels read by assistive technology. Durations are estimates from samples;
unobserved intervals are excluded, and Unknown does not mean absent.

Use **Engines → Add engine** to save an inference profile. The Antec connection is filled in;
connection details remain in an expandable section. **Save engine** stores the profile only.
**Use engine** selects it for all observations. You can keep several named profiles and edit
them independently. Editing the selected profile does not change the running engine until
you select **Use engine** again. Replacing a saved key also leaves the active key unchanged
until selection. **Check connection** tests the selected engine without a camera image.
There is no automatic model substitution. Engine selection and camera configuration are independent.

Failures show a short explanation and **Retry automatically**, with detailed codes expandable.
If a camera times out before it supplies an image, inference is not run. The result remains
Unknown and shows a camera recovery link. Open that camera and select **Test camera** to check
its connection before you try Observe again. A missing inference time is not a zero-second run.
Manual session controls remain on the selected engine page; connection fields are in its editor.
Question ID, timing, ROI and confirmation options are also advanced. A saved paused source stays
paused. Camera addresses/passwords and the question itself still require your one-time input.

If saved camera details appear unavailable after a restart, they may still be intact. Close
the VOP terminal and reopen **Start VOP** before re-entering credentials. The authenticated
`/api/v1/health` response includes `camera_setup` readiness without camera addresses or passwords;
checking it never connects to cameras. Protected-store failures log only their error category
and Windows error number in the terminal. An invalid saved address now has a separate message.
The recurring post-reboot process discrepancy is still under investigation; this is not a claim
that physical reboot recovery has been fixed.

## Install and validate (advanced)

```powershell
# Run from your VOP checkout:
git switch main
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools\phase2_smoke.py
.\.venv\Scripts\python.exe tools\phase3_smoke.py
.\.venv\Scripts\python.exe tools\phase4_smoke.py
.\.venv\Scripts\python.exe tools\run_dashboard.py
```

Create the venv first (`py -3.11 -m venv .venv`) for a new checkout. The smoke script uses a
temporary synthetic database/key and prints `result: PASS`. Use **Start VOP.cmd** for automatic
browser sign-in. Advanced API/manual clients can add `--show-access-key` to the launcher command.
The service runs in that terminal; Ctrl+C stops it.
The default synthetic/mock setup needs no GPU, d1-3B weights or camera. An existing `VOP_API_TOKEN`
can be used; a generated key changes on restart. Neither key is stored in the application DB.

Try **Run synthetic demo** to record six rapid, explicitly mocked samples and a closed episode.
Use **Capture once** to inspect the privacy-masked frame, optional ROI outline, native fields and
provenance. **Questions → Edit** creates a new immutable version; old observations/events keep
their original version. Binary, choice and ordinal questions validate their respective criteria.
The question editor switches criteria when **Answer kind** changes: binary threshold and
episode-confirmation settings, named choice options, or ordered ordinal levels. Irrelevant
controls are hidden and disabled; observation gap, ROI and enabled state apply to every type.
The synthetic preset, when using the local mock backend, also describes the selected type.
Question IDs are generated automatically when left blank. Manual IDs accept 1–64 ASCII letters,
digits, dots, underscores or hyphens, with no spaces.
Choose an unused ID within that source; `new` is reserved for the editor route. IDs become
read-only after creation. Browser validation and server validation enforce these rules.
Type switching uses a small authenticated same-origin script with no external library or inline
code. With scripts disabled, use the type links before entering a question.
The mock preset is a user-selected synthetic answer, not computer vision. Its per-source/version
override survives restart. Unconfigured mock questions return unsupported instead of fabricated
answers. The source and model interfaces remain independent; Phase 4 worker setup is described below.

**Cameras → Manage camera** controls enabled state, image saving
and sample interval. Other inputs use **Settings → Other inputs → Edit source**. A nonzero
interval (1–3600 seconds) explicitly starts background sampling, independent of browser tabs;
0 stops it. Saved sampling controls resume after restart. There is one worker and zero queued
frames; missed/busy samples are dropped and audited, failed sources back off up to 300 seconds.
The overview shows sampling status; use **Refresh view** to refresh the native HTML. Heavy injected
inference retains the Phase 1 soft deadline and can occupy the slot until process restart;
hard real-model isolation remains later work, not an unattended-production claim.

**Sources / Cameras → Remove…** removes an input from active configuration while
keeping history and protected credentials. Restore is available for retired cameras
and removed inputs. Source restore leaves monitoring and evidence retention off.

**Questions → Delete question…** opens a confirmation showing the recorded data to
be deleted. There is no recoverable question removal or keep-data option. Previously
removed questions appear in the same Questions list and can be deleted there; no
Restore action is shown. Old question Remove/Restore links open deletion confirmation
without changing data. Cameras retain their separate recoverable removal workflow.

Choose a camera-name selector button or **All sources** to filter Questions. The
compact list shows all-version answer, image, episode and alert counts. Questions opens from configuration only. Recorded-data counts load separately,
without delaying edit/delete controls. If counts fail, use **Retry counts**; deletion
confirmation still calculates its own current counts. Listing uses count-only aggregate
queries on indexed metadata, not complete deletion previews. Tick several rows and
choose **Delete selected…** for one atomic batch. Review the shared-image warning
before confirming. Deletion waits for current observation/alert work; keep the page
open. The counts are a preview: confirmation covers all data for the selected
questions, including observations recorded before deletion obtains its lock. The
camera does not need to be paused. Other questions continue monitoring afterwards.
New answers, image retention/deletion and episode/alert updates do not force repeated
confirmation. Changes to the selected question setup or its alert-rule configuration
still require a fresh review; deleted IDs remain reserved.

Confirming question deletion opens a **Deleting questions** dialog with an animated
progress bar. It remains while VOP waits for active work and deletes the data;
the result or a fresh-review page then appears automatically. The bar has no
percentage or time estimate because the database change commits in one transaction.
Keep the page open. Escape does not dismiss the active dialog, and repeat submissions
are blocked. Without JavaScript or native dialog support, normal form submission
still works: wait for the result page. Going Back restores the confirmation controls;
the server still checks whether the selected questions can be deleted.

On startup VOP adds a small capture-to-observation lookup index to existing
workspaces. This avoids scanning the whole observation table for each capture during
deletion and foreign-key checks. Confirmation previews read counts and rule setup,
not every raw capture result; deletion loads the current results only when needed.
Repeated rule checks reuse each question's summary within one evaluation cycle;
the next cycle reloads current configuration and data. Notification deliveries and
live answer details are read in batches. Retention skips raw histories/images it has
already cleared. Backup/restore checksums stream files rather than loading the
whole database into memory. Question-history and latest saved-image lookups have
matching indexes installed on startup.

Saved-image clearing and the final database checkpoint can still take time. Do not
force a restart to install an update while a deletion is running; let it finish first.

Deletion erases all versions’ answers, deletion-gap markers, associated saved images,
raw engine details, episodes, alerts and delivery records. Shared images disappear
from other questions’ results too; their typed answers remain. Related alert rules
are disabled. Unrelated captures and other cameras are kept. Failures roll back the
batch. Immutable question definitions, reserved IDs and audit records remain to prevent
old configuration from recreating deleted questions. Backups, exports and messages
already sent are unchanged. There is no Undo. The deletion survives restart and
backup/restore; an older backup can still restore its older setup. Leave the ID blank
when adding a replacement question. Deleting every question is supported.

Observe uses camera-name buttons. Select several to show those cameras together;
select **All cameras** to reset the filter. This changes the display only, not monitoring.
The page uses the configured workspace timezone without a timezone selector. Refresh view keeps
all selected cameras. **Individual Observations** and **Episodes
(Contiguous active observations)** use the same multi-select buttons. Choose several cameras to combine
results in time order; All cameras clears the filter. Older answers keeps every
selected camera. Individual Observations shows image-saving information per selected
camera; Configure mode retains a separate Delete input history action for each camera.
Retired cameras stay out of the selection buttons; existing individual-history links
still work. Episodes uses the configured workspace timezone without
a timezone control. Trends also uses multi-select camera buttons and the workspace
timezone. Its camera buttons preserve the applied dates; Apply dates preserves all
selected cameras, and auto-refresh retains the complete URL. Camera setup uses one Manage camera button per camera, with tighter rows.

### Episode timeline

In View mode, **Episodes (Contiguous active observations)** shows the total recorded
episode count beside each camera name. Select several camera buttons to compare
them. Counts are all-time; the timeline displays up to the latest 1,000 matching
episodes, and the table below retains the latest 100 details.

Use the zoom slider, **+**, **−** and **Fit**, then scroll horizontally through time.
Camera/question labels and the time axis stay visible while scrolling. Each row
represents a camera, question and immutable question version. Select an episode to
inspect its first individual observation; hover or keyboard-focus for context.
The chart uses the workspace timezone and does not start monitoring or inference.

Solid blue bars represent recorded active intervals; amber dashed lines mark
unobserved gaps. Dots mark confirmed starts, including episodes that have no stored
interval yet. Adjacent sampled intervals are merged for display. An open episode
ends visually at its last recorded sample, never at the current clock time. The
existing unknown-gap policy can retain one episode across a gap; the gap remains
visible and does not count as active time. The new title does not change this policy.
The page is a snapshot: refresh it to load newer episodes. Zooming and scrolling
stay local and do not reload the page. Without JavaScript, the SVG, native scrolling
and episode links remain available, but zoom controls need JavaScript.

### Unified camera settings

Use **Cameras → Manage camera**. One page contains
Camera (name), Connection (model/address/account for network cameras), Observations
(enabled state and sample interval), and Recorded images (save images). One Save
settings button saves the form. Save and test connection saves the current form and
then runs the explicit network-camera connection test. Last-test status, Questions
and Remove camera are on this same page. USB cameras use the same observation/image controls
and show their existing device connection. Old /edit and /rename links redirect to
the same canonical camera page; there is no separate overview/edit workflow.
Old camera observation and rename links open this editor. Other input types retain
their existing observation editor.

Leave the network camera password blank to keep it. A changed username can reuse
that saved password. Invalid intervals are rejected before any protected connection
values are written. Connection-only legacy requests retain saved observation settings.
Saving waits for active acquisition; it does not require pausing monitoring first.
A nonzero interval starts repeated observations only when Camera enabled is on.

### Question help and observation frequency

Question editors explain every field in **Advanced: detection and episode settings**
and **Advanced: observation settings**. Yes/No confirmations count consecutive valid
answers, not time. The maximum observation gap controls coverage/unknown intervals;
it does not control how often images are captured. ROI limits this question to a
normalised rectangle; leave it blank for the whole image. The hold-for-review gap
policy has no separate approval action in the editor: choose Resume or Split and
save a new version to resume automatic episode classification.

Observation frequency is set **per camera** at **Configure mode → Cameras → Manage
camera → Observations → Sample interval**. The question editor links
there too. The interval applies to all enabled questions on that camera. It is a
target: cameras take turns, and processing time or connection retries can increase
the actual interval. `00:00:00.0` pauses monitoring; for example, `00:00:10.0` requests
an observation every `00:00:10.0`. Keep the question’s maximum gap long enough for
the expected interval and normal capture/engine delays.

### Remove setup or delete recorded data

Removal and restoration wait for current observation/alert work instead of returning
a busy error. Keep the request page open until it completes; saved history is retained.

- **Cameras → Manage camera → Remove camera…** is visible on each camera row and its detail page. Removal stops using
  that camera and keeps history and protected details. **Retired Cameras → Restore** brings it
  back with monitoring and evidence retention off. **Questions → Delete question…** permanently deletes the question and its recorded data.
- **Engines → Delete…** deletes a saved profile after confirmation. Select another engine first
  if that profile is selected; VOP never chooses a fallback. Model files, protected keys and
  recorded observations are kept. Shared keys are not erased by profile deletion.
- **Configure mode → Settings → Manage saved data → Delete capture…** previews deletion of every answer that shares that capture,
  its raw result and its retained image. It deletes related alerts/delivery records, pauses
  affected alert rules, and rebuilds episodes/metrics from remaining history. A timestamp-only
  gap marker remains to prevent charts from joining across deleted data; it is not a model
  answer and is excluded from answer counts and model provenance.
- To clear an input's recorded data, select it on **Individual Observations**, then choose **Delete input
  history…**. Pause its monitoring first. This also removes deletion-gap markers. Camera setup,
  questions and engine profiles remain. You can review history for a removed input here too.

Delete actions show effects and require confirmation. Changed configuration must be reviewed again;
question deletion covers new data as described above, while history-only deletion retains its current-data check;
GET links never delete. There is no Undo for permanent data/profile deletion. Audit records,
backups and messages already sent remain. Retained images can also be deleted independently
on observation detail pages without deleting measured answers. No user data is deleted merely
by installing this update or opening a page.

Temporal states are **UNKNOWN**, **INACTIVE**, **PENDING**, **ACTIVE**, **RECOVERING** (binary), or
**OBSERVED** (valid choice/ordinal). Binary activation/recovery use configurable confirmation
counts (default 2/2). Episodes start at the activation-confirmation timestamp and close only
after confirmed negatives. Error, unsupported, missing and stale samples remain UNKNOWN.
Gap policies: **resume** after reconfirmation, **split** into an interrupted/new episode without
claiming a negative end, or **manual review** (remains UNKNOWN until an operator reviews history
and saves a new version). A revised question supersedes any old open episode without fake closure.

**Events** shows the latest 100 recorded episodes. **Metrics** provides camera/date
filters, counts, estimated sampled durations, rates per covered hour, occupancy/coverage,
choice dwell and ordinal SVG trends. UTC instants remain intact; timezone labels include offsets
and distinguish repeated DST hours. Date filters are local-calendar inclusive dates converted
to UTC intervals; clipping does not restart an already active episode. UNKNOWN intervals break
chart lines. No observations/eligible interval displays **No data**, not a fabricated zero.
Amber chart bands mark those unobserved gaps; points on either side stay disconnected. Hover
over a point or band for timestamps and interval details. Horizontal positions show sample
order with equal spacing, rather than elapsed time. Sidebar buttons use dark text on pale
backgrounds, including hover, so the navigation controls retain readable contrast.
Durations interpolate only bounded intervals with successful endpoints; they do not prove
continuous visual truth. Rates from tiny samples are not forecasts. Ordinal levels are not
physical measurement units or a universally calibrated confidence.

**Evidence is off by default.** When enabled per source, only a privacy-masked PNG preview
(up to 1920×1920, original metadata stripped) is retained in SQLite. Query ROI crops are applied
after privacy masks; compatible ROI groups share the original frame identity while preserving
all native provider outputs/usage. Source `settings.privacy_masks` is an optional list of
normalised `[x,y,width,height]` rectangles in the private operator configuration. A single masked
preview can also exist temporarily in memory for immediate inspection without retention.
Retained frames and previews require operator access; viewers get 403. Deletion removes the BLOB,
clears the matching in-memory preview and checkpoints SQLite with secure deletion enabled.
It cannot retract copies already made by users or externally managed backups.

Browser login uses a signed HttpOnly/SameSite=Strict cookie lasting up to 14 days since
the last authenticated request; Sign out clears it immediately. Expired pages stop background
network polling and show a sign-in message without discarding unsaved changes. Open Start VOP
to sign in again, then reload the old page. Monitoring runs independently of browser sign-in.
Repeated denied requests are audited once per category per minute to avoid a polling write storm.
Write forms require CSRF
and same-origin checks. Optional read-only access uses a distinct `VOP_VIEWER_TOKEN` set before
startup (same 32–256 ASCII-character requirement). Viewers can inspect metadata/metrics, but cannot
capture, edit, sample or access image evidence. There are no individual user accounts or SSO.
Bearer API access continues to work. Long-lived keys never appear in login URLs; desktop launch
uses an authenticated, one-use ticket valid for 60 seconds. There are no external scripts/CDNs, SPA or frontend
build tooling is used. Templates escape user text, and CSS respects reduced motion.

Additional authenticated APIs: `GET /api/v1/events`, `GET /api/v1/metrics`, `POST /api/v1/replay`.
**Settings** also permits an idle, operator-requested deterministic replay. SQLite schema v2
upgrades v1 transactionally, retaining observations and making a consistent
`<database>.v1-backup.sqlite3` before migration. Existing UI revisions/controls win over unchanged
bootstrap config on restart. New declared config versions can be activated; historical versions
cannot be edited. Late frames are retained/audited but excluded from live state/event replay.

## Authorised USB test and remaining hardware limits

The owner authorised a brief USB test on this Dell. Index 0 returned a real **640×480 PNG**.
Two subsequent USB captures traversed mock inference, storage and dashboard rendering: six
observations, HTTP 200 dashboard, mock ACTIVE binary state. **No camera pixels were retained
or committed, and no real-model inference ran.** This validates capture/software, not model
accuracy. Tapo/RTSP hardware is untested because no authorised endpoint/configuration was supplied.

For an explicitly authorised future USB session, install `.[camera]`, prepare ignored
`config.local.json` with kind `usb` and `settings: {"device":0}`, and run:

```powershell
.\.venv\Scripts\python.exe tools\run_dashboard.py .\config.local.json --allow-live-sources
```

Startup/sample controls never bypass the live-source opt-in. Network-camera endpoints remain
environment references with exact allowed-host policy; do not paste credentials into repo/UI.
Real d1-3B CPU feasibility remains the separately recorded Phase 0 server result; no GPU,
remote-worker, model-format or accuracy claim is added. See `CODEX_PHASE_2.md` and
`reports/phase2-validation.md` for gates, actual commands and limitations. The checked
[Windows/Ubuntu Actions run](https://github.com/VibeCoder01/VOP/actions/runs/38452430979) passed
installation, regressions, mock demo and both actual HTTP/restart smokes. Licence decisions
remain separate. That Phase 2 evidence is historical; see the Phase 3 report for current checks.

## Phase 3 release tools

Restart the dashboard after updating to Phase 3; the existing browser process keeps its old code
until stopped with Ctrl+C. Schema v3 migrates v2 transactionally and retains
`<database>.v2-backup.sqlite3` for rollback with the previous app. Never downgrade a v3 database.

Open **Alerts and release tools** in the sidebar. Create a binary duration rule (sampled seconds
greater than a threshold) or an episode-count rule (count greater than N in a moving interval).
Rules apply to the current question version; query edits do not reuse old observations. Saving
a rule makes a new immutable revision; old alerts retain their criteria/version/provenance.
The duration rule emits at most one alert per episode. Count/health rules emit once per transition.
UNKNOWN suspends detection re-arming rather than implying an all-clear. Source-offline and
processing-degraded rules are distinct. Offline alerts require enabled sampling and an observed
disconnect/stale condition. A stopped source does not assert a detection or connectivity result.
Each alert records its mock/model provenance. Operator acknowledge, resolve and notes are audited;
resolving an alert does not close the measured episode or change the underlying observation.
Filter alerts by source, question, severity and UTC interval. Latest 1,000 matching alerts are shown.

The alert worker runs independently of browser tabs. Dashboard delivery is durable by default.
Optional webhook delivery requires checking the rule's webhook box **and** explicit server
environment configuration: `VOP_WEBHOOK_URL` (HTTPS), `VOP_WEBHOOK_ALLOWED_HOSTS` (comma-separated
exact hostnames) and optional `VOP_WEBHOOK_TOKEN`. These values are never saved in SQLite or
exports. There is no default outbound destination. TLS certificate validation is enabled;
redirects and inherited proxies are disabled. Explicit allow-listing permits an authorised private
receiver; do not expose an arbitrary user-supplied endpoint. No email transport is implemented.
The same `Idempotency-Key` is sent on every attempt; the receiver must deduplicate it. Delivery
is at-least-once after an ambiguous timeout/crash, not a guarantee of exactly-once reception.
Five attempts maximum, capped retry delays, five-second HTTP timeout, and visible delivery failure
bound the worker. A restart retries an interrupted attempt without generating another alert.

CSV/JSON event, metric and alert downloads include source/question versions, timezone and recorded
provenance, excluding image pixels and credentials. CSV protects spreadsheet formula prefixes.
Viewer access permits these metadata exports; configuration export, audit and maintenance require
operator access. Export configuration includes file references and secret environment *names*,
not their values. The service also exposes `GET /api/v1/alerts`. Login attempts are capped at
20 per minute for this loopback, single-operator process.

Retention has an explicit preview and apply step. No policy deletes data by default. Applied
evidence/raw-provider-detail/audit windows run hourly while VOP runs. Normalized observations,
frame hashes, query history and events remain to preserve deterministic replay/metrics; this
is not full history erasure or a database size quota. Existing backups and downloaded copies are
operator-managed and are not erased by retention. Backups can contain retained evidence and need
the same access protection as the live data. Stop VOP for offline configuration import/backup:

```powershell
.\.venv\Scripts\python.exe tools\release.py export-config --config sample-config\phase1.json --output config-export.json
.\.venv\Scripts\python.exe tools\release.py import-config --input config-export.json --output imported
.\.venv\Scripts\python.exe tools\release.py backup --config sample-config\phase1.json --output backups\before-update
.\.venv\Scripts\python.exe tools\release.py restore --input backups\before-update --output restored\test
.\.venv\Scripts\python.exe tools\run_dashboard.py restored\test\config.json
```

Import/restore create a new directory and refuse overwrite. Configuration import validates schema,
query policy, rules and references before writing the destination. Backups use SQLite's backup API
(including committed WAL/evidence), a configuration snapshot, integrity/foreign-key checks and
SHA-256 manifest checks. Checksums detect corruption; they do not authenticate an untrusted backup.
Keep these exports/backups outside version control. Never substitute a backup under a running app.

Build the development release with `python tools/build_release.py`. The output ZIP in `dist/`
contains a VOP wheel, locked dependency list, synthetic fixture, Windows installer and runbook;
local data, access keys, camera images and weights are excluded. See `install/README.md` for fresh
installation and rollback. This package requires Python and dependency installation; it is not
a standalone executable or unattended Windows service. It retains the local-development defaults.

See `CODEX_PHASE_3.md` and `reports/phase3-validation.md`. Production release acceptance remains
conditional on actual RTSP/reference-camera and workload accuracy validation, licence review,
OS secret protection and deployment hardening. No new real-model/GPU/remote-worker measurement
is claimed. This was the Phase 3 boundary; Phase 4 has since received separate authorisation.

Opt-in online dependency check: `python tools/dependency_audit.py --allow-network` queries the
[OSV API](https://google.github.io/osv.dev/api/) with public package names/versions from the
pinned offline dependency list. It does not send configuration, images or secret values.
The Phase 3 scan prompted verified updates to Pillow 12.3.0, setuptools 83.0.0, pytest 9.0.3
and Pygments 2.20.0. Historical Phase 0 server lock/results remain unchanged; that old model
environment is not the current development release or a production security recommendation.

## Phase 4: GPU worker and protected camera setup

### Daily use

On Windows, double-click **Start VOP.cmd** in the VOP folder. It opens the browser and starts
the local app with camera support. Keep its terminal window open. The launcher stores its
operator access key using Windows DPAPI and reuses it internally on later launches. No key is
printed unless `--show-access-key` is requested. Existing instances are authenticated and their
listener ownership/launcher path checked before a one-time browser ticket is issued. An
unrelated port listener is not given a key or taken over. An unreadable saved key is never
silently replaced. Close/reopen VOP if an older running instance cannot authenticate the launcher.

Normally **Observe now** manages the connection for you. The following optional manual controls
remain under **Advanced connection settings** (or launch with `--manual-worker`):

1. Choose a **15, 30 or 60 minute** session and press **Start antec session**. The button
   opens the SSH tunnel and temporarily pauses the
   existing `llama-mtp.service` if it was active. No images are sent by this action.
2. After a few seconds, press **Test worker identity and health**. It must show a ready real
   worker on CUDA before relying on its results. A requested session alone is not proof of readiness.
3. Enable the camera and at least one question in Sources / Questions. Keep its interval at **0** for manual captures and leave
   evidence off. Use **Capture once**, then **Capture again** on the readable result screen.

**Stop session and restore workload** ends an app-owned session early. The remote helper also
ends it when its bounded lease expires or the SSH input closes; the app requests cleanup on
shutdown. Only a workload active before the session is restarted. This is a foreground,
owner-started pilot session, with no persistent service or automatic startup installation.
The controls currently target the already-verified `antec.local` installation and its pinned
worker paths. Another deployment can still use its own manually configured worker/tunnel.
If port 8878 already belongs to a tunnel, VOP refuses to take it over: test that existing
connection instead. SSH must already have trusted host keys and working noninteractive login
for the current Windows user; VOP does not bypass host verification or collect SSH passwords.

Worker health and capture results are shown in plain language. Expand **Connection details**
or **Technical details** for native provenance and raw scores. A failed inference stays Unknown;
it is never displayed as an absent person. Session controls do not change sampling, evidence,
camera credentials. No permission checkboxes are required: selecting a worker enables its use
by the dashboard; **Start session** requests the stated temporary workload pause, and **Test camera**
requests one local preview. Camera save, camera test and observation are separate actions.

Use the separate **Cameras** and **Engines** pages in the sidebar. Operator access and CSRF are required; viewers
cannot see credential forms or invoke connection tests. Live capture and remote transmission
are independent settings. Saving/checking a camera never starts scheduled sampling. The dashboard launcher
uses the saved selected worker after restart, without requiring permission to be ticked again.
The lower-level API/service and remote-engine constructors retain their explicit transmission
opt-in; the dashboard's worker selection/capture action supplies it. Authentication, CSRF,
endpoint restrictions, evidence retention controls and model-download opt-ins remain enforced.
Local mock stays available and clearly labelled; there is no automatic mock/CPU fallback.

**Needs attention** panels beside actions link to missing setup. Known failures disable Capture
or Start rather than hiding the control: a disabled source, no enabled questions, missing camera
dependency/address/account, unreadable worker key or previously unavailable worker. A one-shot
dashboard capture checks worker health before acquiring an image. A last successful health check
does not guarantee continued availability; GET pages show local prerequisites and cached results
without connecting to cameras or workers. Test health again after starting/fixing a worker to
clear a failed check. Camera preview tests work independently of source enabled state and worker
readiness. For scheduled sampling, the existing bounded error/UNKNOWN behavior remains in place.

Colour reinforces text throughout the app: blue actions/information, teal ready/success, amber
missing prerequisites/unknown states, red failures/removal, and muted disabled states. Disabled
buttons keep their explanatory text nearby; colour is not the only status cue.

For Tapo **C200, C210 and C510W**, register a distinct source ID (for example `tapo-c200`), model,
literal private LAN RTSP address such as `rtsp://192.168.1.100:554/stream1`, and the dedicated
camera account username/password from the Tapo app. Do not put credentials in the address.
The GUI accepts stream1/stream2 on port 554; the existing generic adapter also retains explicit
operator configuration. The new source is disabled with sampling/evidence off and binary query
**“Is there a human in the picture?”**. Correct credentials can be saved repeatedly; a blank
password preserves the existing account. **Test camera** receives one
local frame, show a privacy-masked memory-only preview and store diagnostic metadata; no model
request is made by that connection test. Capture failure never asserts “no human”.

The setup page reopens the saved camera's address, username and model; passwords stay blank.
Use **Cameras → Manage camera** to change a saved camera, or **Add camera**
for an empty form. Save returns to that camera's page; **Test camera** opens the connection result.
The sample IP is a
placeholder only and is never submitted as a default address.

If a connection test reports that another capture is running, wait for that request to finish
before retrying. A capture timeout is a separate camera-connectivity failure. Check the actual
camera IP in Tapo Device Settings → Device Info and its dedicated account in Advanced Settings
→ Camera Account. A refused TCP connection to port 554 occurs before authentication; check the
address, camera availability and RTSP setup before changing passwords.

Windows credential/key values are encrypted with user-bound DPAPI under
`%USERPROFILE%/.vop/secrets`. This location is shared by direct Windows launches and launches
from packaged Codex; AppData redirection previously made them see different saved details.
Missing values are recovered automatically from the previous AppData or Codex LocalCache
vault, validating the most recently saved encrypted file before copying it. Originals are retained, and an
existing value in the shared vault is never overwritten by migration. If the newest old value
cannot be unlocked, VOP reports the problem instead of silently substituting an older value.
`VOP_SECRET_DIR` is an advanced absolute-path override; smoke tests use it for disposable
storage and disable legacy migration there. Configuration, SQLite and exports contain references, not secret
values. RTSP credentials are resolved and inserted into the locator only within the capture child;
native diagnostics are suppressed. Linux camera secret setup requires an unlocked OS Secret
Service (`secret-tool`), rather than falling back to plaintext. After restoring/moving configuration,
re-provision the referenced secrets on the destination host/account. Backups do not copy the vault.

For regular authorised live evaluation, start the dashboard with:

```powershell
.\.venv\Scripts\python.exe tools\run_dashboard.py --allow-live-sources
```

Then enable the configured source in **Sources**. Leave its interval at 0 for manual captures,
or explicitly choose a measured sample interval. Select the authenticated worker profile and
test its health when ready. Privacy masks and ROI are applied
on the capture host before any remote request. Evidence remains off unless separately enabled.

The first remote transport uses SSH forwarding to an antec **loopback** worker. For the verified
installation, the environment/source/cache live under `~/.local/share/vop/phase4`. It was created
without modifying system Python, drivers or existing GPU services. The pinned checkpoint is
`051bcc464b01b9f92942b364d9586b0ef5912432`; the tested NVIDIA path is Torch 2.14.1+cu130,
CUDA 13.0, Transformers 5.19.0, accelerate 1.15.0, BF16. The complete actually installed closure
is `requirements-liquid-linux-cuda.lock.txt`. Vulkan and AMD/ROCm are not tested backends here.

On antec, when sufficient GPU capacity has been made available, run the **foreground** worker:

```bash
vop_root="$HOME/.local/share/vop/phase4"
PYTHONPATH="$vop_root/source/src" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  "$vop_root/venv/bin/python" "$vop_root/source/tools/run_worker.py" \
  --worker-id antec-d1 --token-file "$vop_root/worker.token" --port 8878 \
  --device cuda:0 --precision bfloat16 --cache-dir "$vop_root/model-cache" \
  --allow-model-download --accept-model-risk
```

The worker key file must be owner-only (mode 600); it was generated for the test installation
without exposing its value in logs. The laptop's `antec-worker` reference was protected with
DPAPI for the verified connection. An operator can provision/rotate it in the GUI. For another
installation create a strong key locally, protect the worker file and supply the same key to the
laptop's secret reference. Do not add token files or `.env` credentials to Git.

In a separate laptop terminal, keep the encrypted tunnel open:

```powershell
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=10 -L 127.0.0.1:8878:127.0.0.1:8878 antec.local
```

The GUI worker profile uses engine `liquid-d1-3b`, the pinned revision above, identity `antec-d1`,
URL `http://127.0.0.1:8878`, transport `ssh`, secret reference `antec-worker`, and synthetic **off**.
**Test worker identity and health** sends no pixels and reports actual device/precision/readiness
or a diagnostic. A profile alone is not a working GPU connection. Direct plaintext LAN worker URLs
are rejected; no public worker port, insecure TLS option or automatic SSH host-key acceptance exists.

The existing antec llama workload occupied approximately 10 GB of NVIDIA VRAM. It was paused
only for the expressly authorised benchmark/proof windows and restored afterwards. d1-3B used
approximately 6.3 GB of GPU allocations plus runtime overhead; simultaneous operation is not
promised. Startup conservatively requires 8 GiB free VRAM for GPU BF16/FP16 (14 GiB for GPU FP32)
and 8 GiB available host RAM for GPU,
or 24 GiB available host RAM for CPU FP32, reporting `gpu_capacity`/`host_capacity`. Decide which
workload gets that GPU before sustained live inference. No unattended service/autostart was added.

For a capable local CPU host, run the same worker with `--device cpu --precision float32` and
select transport `local`. This requires its own installed model dependencies/resources and
explicit model consent. The Dell CPU remains unvalidated/infeasible for this model; a mock or
remote worker on the laptop needs no Torch/model weights locally.

Requests carry bounded image bytes and complete question criteria, not file paths. The worker
accepts JPG/PNG up to 20 MiB and 16 megapixels, at most 32 questions, total request 29 MiB,
response 2 MiB, and one active inference with no queue. Bodies have a ten-second read deadline;
inference has a hard child timeout (default 30 seconds), and repeated failures have a bounded
restart/cooldown. Request identities include preprocessed bytes/criteria so ROI groups remain
distinct. Results are cached for 30 seconds with at most 16 entries; stale/deadline/identity/digest
failures become UNKNOWN/ERROR and cannot rewrite already persisted frames/events. Runtime and
worker/request provenance accompany model usage. No incoming worker images are saved by default.

Offline checks use a mock worker and no real cameras/model weights. The actual synthetic HTTP
restart/disconnection smoke is `tools/phase4_smoke.py`; Windows uses real DPAPI while Linux CI
uses an explicitly labelled fixture for secret retrieval. Manual load evidence is generated by
`python tools/phase4_soak.py --seconds 3600 --output reports/local/phase4-soak.json` (synthetic
only). See `reports/phase4-validation.md` for completed measurements and honest pending gates.
Real human-presence accuracy still needs owner-approved labelled frames for each camera; no face
identity, tracking, person count, calibrated confidence or real-time-video promise is made.
Phase 5 Actions and Automations was separately authorised on 27 October 2026.

## Phase 1 historical foundation (v0.2)

The following section describes the earlier Phase 1 baseline. Browser sessions, retained evidence
and schema v2 above supersede its historical no-cookie/no-pixel statements in the current build.

Phase 1 adds validated JSON configuration, a local authenticated service, SQLite observations
and one-shot source adapters to the merged Phase 0 inference contracts. `CODEX_PHASE_1.md`
records the current foundation scope; `SRS-v0.2.md` remains the product specification.
The default pipeline is explicitly **MOCK — no vision**. Model weights are never downloaded
or loaded by service startup. Phase 0 benchmark evidence remains in the existing reports.

### Phase 1 operator quickstart (PowerShell, historical)

```powershell
git switch codex/phase-1  # Until the Phase 1 PR is merged
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -q
# Actual HTTP/restart smoke with temporary token/database; no internet or camera:
.\.venv\Scripts\python.exe tools\phase1_smoke.py
```

Create the venv first with `py -3.11 -m venv .venv` if this is a new checkout. Start a persistent
local service and exercise it from the same PowerShell session without putting the token in
a file or command-line argument:

```powershell
$env:VOP_API_TOKEN = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$service = Start-Process -FilePath (Resolve-Path .\.venv\Scripts\python.exe).Path -ArgumentList '-m vop serve --config sample-config/phase1.json --port 8765' -WindowStyle Hidden -PassThru
$headers = @{ Authorization = "Bearer $env:VOP_API_TOKEN" }
# Wait for startup, without displaying the secret:
for ($attempt = 0; $attempt -lt 50; $attempt++) {
    try { $health = Invoke-RestMethod http://127.0.0.1:8765/api/v1/health -Headers $headers -TimeoutSec 2; break }
    catch { Start-Sleep -Milliseconds 200 }
}
Invoke-RestMethod http://127.0.0.1:8765/api/v1/sources -Headers $headers
Invoke-RestMethod http://127.0.0.1:8765/api/v1/sources/synthetic-scene/capture -Method Post -Headers $headers
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/observations?limit=20' -Headers $headers
# Also accepts encoded JPEG/PNG bytes; frame ID enables safe duplicate detection:
Invoke-RestMethod http://127.0.0.1:8765/api/v1/sources/synthetic-scene/frames -Method Post -Headers (@{Authorization=$headers.Authorization; 'X-Frame-ID'='manual-frame-1'}) -ContentType image/png -InFile .\fixtures\scene.png
# When finished:
Stop-Process -Id $service.Id
```

Alternatively run `python -m vop serve --config sample-config/phase1.json --port 8765` in the
foreground with the same environment secret. The CLI binds **127.0.0.1 only** and all routes
require a 32–256 character ASCII bearer secret. There are no cookies, default credentials,
public health exceptions, account management or permissive CORS. This is a single-operator
development foundation, not a production multi-user authentication system. Rotate the secret
by restarting with a newly generated value; it is never stored in the database or logged.

The sample produces three independent questions over one generated shape image. Capture returns
201 with a run ID, stable source/frame/question provenance, native fields, UTC timestamps and
`synthetic: true`. Persisted observations survive restart; no pixels are saved. SQLite stores
frame metadata, immutable question versions, runs, individual answers and minimal audit events.
Changing question content requires a new version. The initial schema migrates transactionally;
unknown/newer schemas are rejected. Before a future migration, stop the service and back up the
database with SQLite's backup API; do not copy an active WAL database file alone. Roll back by
restoring that backup and the matching application version; no downgrade is attempted.

Endpoints: authenticated `GET /` (diagnostic HTML), `GET /api/v1/health`,
`GET /api/v1/sources`, `POST /api/v1/sources/{id}/capture`,
`POST /api/v1/sources/{id}/frames`, and `GET /api/v1/observations`.
Observation pagination uses `limit` (1–100) and `after` (last sequence); optionally filter by
configured `source_id`. Byte ingestion accepts only JPEG/PNG and at most 20 MiB. A repeated
source/frame ID returns the original result without inference; changed content under that ID
returns 409. A failed capture has **null frame/capture timestamp and null values**, not a fake
image or confirmed negative. Binary answers use positive/negative; valid choice/ordinal answers
have `normalised_state: not_applicable`, without pretending they are binary decisions.

One POST is admitted at a time, with no queued frames; excess work returns 429 and is audited.
Health remains responsive during inference. Capture and inference identities stay independent;
the service never silently substitutes a model. `create_app(settings, engine=...)` accepts an
explicitly prepared engine implementing the Phase 0 protocol, so model code and hardware remain
outside callers. The CLI intentionally uses configured mocks; optional real-model preparation
continues through the explicitly consented Phase 0 tooling. Synchronous inference deadlines are
soft: late results become timeout failures, but a hung injected engine cannot be killed by this
service. Process-isolated real inference/remote workers remain later work; do not deploy this
foundation for unattended heavy models. No new real-model run occurred in Phase 1.

## Optional one-shot camera inputs

Camera inputs require operator-owned `config.local.json` (ignored), explicit
`--allow-live-sources`, and the same authenticated POST capture endpoint. Startup never opens
a device; there is no continuous capture or scheduler. Configuration is read from the local
file, not accepted through an HTTP registration API. Supported source kinds:

| Kind | `settings` | Additional requirement |
|---|---|---|
| `synthetic` | `{}` | No hardware; generated shapes |
| `file` | `{"path":"fixtures/scene.png"}` | Path relative to the configuration file |
| `usb` | `{"device":0}` | Optional OpenCV installation |
| `rtsp` | `{"endpoint_env":"VOP_CAMERA_URL","allowed_hosts":["camera.example"]}` | Optional OpenCV; endpoint set locally in environment |
| `snapshot` | Same environment reference/host list | Stdlib HTTP(S) acquisition |

Use authorised local hostnames in private configuration; the table's hostname is fictional.
Camera URLs and query credentials belong only in the referenced environment variable, not
source control. Userinfo credentials in URLs are rejected. Username/password camera
authentication, discovery and arbitrary redirects are deliberately unsupported at this stage.
Only exact configured hostnames/schemes are allowed; HTTP redirects and inherited proxies are
disabled. The API returns no endpoint, environment-reference or local-path settings.

```powershell
# Only for USB/RTSP adapter use; not installed in CI:
.\.venv\Scripts\python.exe -m pip install -e '.[camera]'
# Explicit live capture consent (foreground example):
.\.venv\Scripts\python.exe -m vop serve --config .\config.local.json --allow-live-sources
```

USB/RTSP/HTTP acquisition runs in a spawned child with a hard total deadline; blocked reads
are terminated and persisted as typed failures. Native camera diagnostics are suppressed to
avoid exposing endpoints. Adapter behaviour is tested with fakes; **no real camera was connected**.
Optional OpenCV installation/version availability is checked separately; codec/hardware support
is not claimed. The allow-list is for operator-controlled destinations, not a general public
URL ingestion service; production DNS/transport and credential policy remain deployment work.

FastHTML/Starlette supplies the local API and diagnostic HTML; SQLite uses the standard library.
There is no React app, dashboard, temporal state machine, event metric, alert, remote transport,
installer, licence selection or Phase 2 implementation. See `reports/phase1-validation.md`.
All 131 local tests passed, and the checked [Windows/Ubuntu Actions run](https://github.com/VibeCoder01/VOP/actions/runs/38433218680)
passed installation, tests, mock demo and actual HTTP/restart smoke on both platforms.

## Phase 0 historical setup and evidence

## Windows 11 setup (PowerShell)

Use 64-bit Python 3.11. The offline stack was tested on Python 3.11.9 / Windows 11 Pro
build 26300 on the Dell Latitude 5510 / i5-10310U. Installation needs internet or a wheelhouse;
tests and demo need no internet, model dependencies, weights, GPU or credentials.

```powershell
git clone https://github.com/VibeCoder01/VOP.git
Set-Location VOP
# Until merged, select the implementation branch:
git switch codex/phase-1
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m vop demo --image .\fixtures\scene.png --engine mock
.\.venv\Scripts\python.exe -m vop check-env
```

Expected: tests pass; `pip check` finds no broken requirements; demo exits 0 with
`synthetic: true`, `engine_id: mock`, the label `MOCK — no vision` and three independent
answers sharing one `frame_id`. The mock returns configured values, never examines pixels.
`check-env` prints OS/build, CPU, RAM, disk and dependency versions. Controller inventory
does not establish accelerator runtime compatibility.

The offline dependency closure and build backend are pinned in `requirements-offline.txt`.
For air-gapped installation, populate a wheelhouse on the same Python/OS/architecture with
`python -m pip download -r requirements-offline.txt -d wheelhouse`, then install with
`--no-index --find-links wheelhouse -r requirements-offline.txt`. Editable installation uses
the installed backend without dependency downloads. The abstract-shape fixture can be recreated:

```powershell
.\.venv\Scripts\python.exe .\tools\generate_fixture.py
```

## Portable contracts

`FrameEnvelope` carries image bytes, source/frame IDs, SHA-256, dimensions and UTC timestamps.
Only `FileImageAdapter` accepts a path. JPEG/PNG are detected by contents and fully decoded;
missing, unsupported and corrupt inputs raise typed `ProviderError`. Imported file capture
time is unknown: `captured_at_utc` explicitly uses the import instant.

`QuestionSpec` declares kind, version, criteria and binary threshold. An `InferenceRequest`
groups independent questions over one frame and optional UTC deadline. Callers use
`InferenceEngine` and `infer(engine, request)`, without model classes, paths or device assumptions.
Two mock engine instances are interchanged through that caller in offline tests. Capabilities
and engine identity are independent of source IDs. Future GPU/CPU or remote engines can
implement the same interface; transport, scheduling and automatic fallback remain deferred.

`InferenceResult` retains source/frame/question provenance, capture/completion timestamps,
elapsed time, native outputs, usage, revision and explicit `success`, `unsupported`, `timeout`
or `model_failure`. Failed answers have `value: null`, never fabricated negatives. Binary
scores retain their threshold and `calibrated: false`; choice confidence and ordinal expected
levels preserve distinct semantics and all native fields/extensions. This is not an accuracy
or temporal-measurement implementation. Synchronous deadlines are checked before/after calls;
only the benchmark child has a hard timeout that interrupts execution.

## Optional benchmark — explicit operator action

The [official API/source](https://huggingface.co/LiquidAI/d1-3B/blob/051bcc464b01b9f92942b364d9586b0ef5912432/README.md)
was inspected at SHA `051bcc464b01b9f92942b364d9586b0ef5912432`. Runtime validation and
measurements are recorded in `reports/`; source inspection alone is not a successful model run.
`requirements-liquid.txt` contains separately installed direct runtime pins. The validated
Linux x86_64 / Python 3.14.4 CPU closure is in `requirements-liquid-linux-cpu.lock.txt`;
the optional Windows model runtime remains unvalidated.

The Dell inventory showed about 5.4 GiB available RAM and 14.5 GiB free disk. These are inventory
readings, not measured model usage. Its inference outcome remains `not_run`; CPU-model feasibility
on the Dell cannot be inferred from a run on another machine. An independently provisioned
server can run this same CLI; its measurements must remain separately labelled.

Inspect inventory and generate a declined-consent report (no download; expected exit 2):

```powershell
.\.venv\Scripts\python.exe -m vop check-env
.\.venv\Scripts\python.exe -m vop benchmark --engine liquid-d1-3b --image .\fixtures\scene.png --reference-dell
```

Only if choosing to install the runtime and accept resource/checkpoint-code risks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-liquid.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m vop check-env
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
Remove-Item Env:TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m vop benchmark --engine liquid-d1-3b --image .\fixtures\scene.png --reference-dell --allow-model-download --accept-model-risk --timeout-seconds 900 --repeats 3
```

Both consent flags are required; without both, `not_run` is recorded and no child starts.
Consent includes downloading several GB and executing checkpoint Python with
`trust_remote_code=True`. Only the pinned official snapshot is accepted; the adapter loads it
locally with pinned code, `local_files_only=True`, `dtype=torch.float32` and `.to('cpu')`.
Internal tokenizer/processor lookups use that snapshot too. Calls use
`model.system_one(None, questions, images=[image])`, mapping binary → noul, choice → choice,
ordinal → score. No chat generation, silent FP16 conversion or Vulkan runtime is used.

Preflight conservatively requires **16 GiB available RAM** and **20 GiB free cache disk**;
these are experiment thresholds, not safety guarantees or measured requirements. A nominal
16 GiB laptop usually fails the RAM threshold. FP32 weights alone are estimated at about
12.5 GB before runtime overhead. After reviewing the risk, an operator may add
`--override-preflight` for that one command. This never disables the watchdog or 2 GiB reserve.
Another local cache disk can be selected with `--cache-dir D:\VOP-model-cache`.
`--reference-dell` rejects a mismatched host; omit it for a separately labelled server run.

The child has a total download/load/inference timeout. It is stopped if sampled available
RAM falls below 2 GiB or process-tree RSS exceeds starting available RAM minus the reserve.
100 ms sampling can miss peaks; RSS is not total committed memory, and this cannot guarantee
protection from pagefile stress or sudden allocations. Partial results survive failures.

Reports distinguish `not_run`, `blocked_preflight`, `passed`, `failed_oom`, `failed_dependency`,
`failed_runtime` and `failed_timeout`. Actual runs record revision/cache path and hub blob hashes
where available, dependency versions, image hash/dimensions, separate download/load timings,
sampled peak working set and minimum available RAM, and actual raw/normalised outputs for
1/3/5 questions. Each shape has a first call and at least three warm samples, median/maximum.
The 1-question first call is first ever inference; 3/5-question calls follow earlier cases.
p95 remains null below 20 warm samples (`--repeats 20`). Timings include adapter validation.
`passed` means valid API output, not validated speed or accuracy.

Reports default to ignored `reports/local/`. Review generated paths/log tails before sharing.
Exit codes: successful demo/check-env 0; image/CLI failure 1; benchmark passed 0, otherwise 2;
argument misuse 2. Synthetic mock outputs are never included as real benchmark evidence.

## Actual alternate-server CPU result

The owner accepted alternate-server CPU feasibility as sufficient for Phase 0. The official
FP32 benchmark **passed**, with 12 valid calls over the same 384×256 synthetic image. All floating
parameters were separately verified as `torch.float32` on CPU (3,123,483,888 parameters).

| Questions | First call | Warm median | Warm maximum | Warm samples |
|---|---|---|---|---|
| 1 | 8.526 s | 6.745 s | 6.746 s | 3 |
| 3 | 9.473 s | 9.437 s | 9.485 s | 3 |
| 5 | 11.380 s | 11.307 s | 11.394 s | 3 |

Model-load stage: 1.294 s after download; download/cache resolution: 125.336 s. First inference
includes lazy runtime/processor setup outside the load stage. Sampled process-tree peak RSS:
**17.700 GiB**; minimum available RAM: 26.779 GiB. Sampled child-tree swap peaked at 328.422 MiB,
below the 512 MiB watchdog threshold; this is not zero paging. Linux child-tree swap above
that threshold produces `failed_oom`; Windows per-process swap is not measurable by this tool.
These results support sparse still images on this server. Median throughput is approximately
0.148/0.106/0.088 images per second for 1/3/5 questions, derived from recorded median latency.
GPU and Dell performance were unmeasured in Phase 0; the Phase 4 GPU evidence is recorded above. See `reports/alternate-server/phase0-report.json`
and `.md` for actual native outputs. **GO** for Phase 1 foundation review under the accepted
server criterion; Phase 1 work itself still requires explicit authorisation.

For a matching Linux CPU environment, create a venv and install
`requirements-liquid-linux-cpu.lock.txt`, then install the package with
`python -m pip install --no-deps --no-build-isolation -e .`. Run the same benchmark command
with Linux paths and without `--reference-dell`. This is standalone CLI execution, not a worker
deployment service. Without ensurepip, use `python3 -m venv --without-pip .venv`, then
`python3 -m pip --python .venv/bin/python install pip -r requirements-liquid-linux-cpu.lock.txt`.

## Evidence, decisions and limits

History-deletion tests use explicit synthetic captures with background sampling and alert
workers disabled. They exercise busy-lock rejection explicitly, so background scheduling
does not make deletion assertions depend on runner timing.

- `reports/phase0-report.json` / `.md`: Dell inventory and honest feasibility outcome.
- `reports/phase0-validation.md`: commands, results, changed files and all ten acceptance criteria.
- `decisions/ADR-0003-phase0-feasibility.md`: Phase 0 recommendation and real-engine decision.
- `.github/workflows/offline-tests.yml`: Python 3.11 tests on Windows/Ubuntu. Setup fetches only
  offline dependencies; test sockets are denied, Torch is absent and models are never downloaded.
  Both jobs passed in the checked [initial PR run](https://github.com/VibeCoder01/VOP/actions/runs/38429400246).

Model load, throughput and workload accuracy must be validated before choosing a production
engine. A server benchmark does not prove Dell feasibility. Alternative models/runtimes require
explicit image/API-equivalence, licensing and accuracy checks through the same contracts.
Capture, inference, storage and UI placement remain independent; the Phase 4 worker adds an authenticated transport.

The application licence remains **undecided**. The model's
[checkpoint licence](https://huggingface.co/LiquidAI/d1-3B/blob/051bcc464b01b9f92942b364d9586b0ef5912432/LICENSE)
requires independent review before intended use/redistribution. No model weights, credentials,
real camera images or private network configuration are committed. Repository visibility remains
unchanged. The SRS and accepted ADRs remain the architectural baseline.

**Phase 5 Actions and Automations is authorised. Phase 6 requires explicit new authorisation.**

### Reading Trends and testing cameras

Trends uses **Observation coverage** (higher means more complete timing evidence,
not greater model accuracy) and **Condition active** (share of covered time with a
Yes answer; whether higher is desirable depends on the question). Both have help
on hover and keyboard focus. The daily-count/choice-dwell panel is removed.
Durations use hours:minutes:seconds with one decimal second, for example
`01:02:03.4`; hours can exceed 24. Duration form fields accept this format. Counts
remain whole numbers; displayed rates, percentages and numeric answers use one
decimal place. Stored values, technical JSON and downloads retain their precision.
Question answer type `binary` is labelled **Yes/No** in the interface.

**Save camera** waits automatically for the current observation or configuration
request to finish. Keep the page open while the button shows Working; monitoring
can stay on. Protected address/account changes and saved configuration are applied
under the observation lock, so waiting does not change a camera partway through
acquisition. Saving alone does not connect to a camera or run inference.

**Test camera** runs immediately when free. Otherwise it schedules one connection
test per camera for the next available slot, ahead of periodic observations, and
opens a result page that updates automatically. The test does not require an
active question or enabled monitoring, invoke inference, or retain image evidence.
Its temporary preview can expire when a later capture from that same camera replaces it. Pending tests
are held in memory: after restarting VOP, request the test again. This does not
change the overload behavior of the machine API.

### Settings and the live workspace

Open **Configure mode → Settings**. Each task has its own tab: **Notifications**,
**Rules**, **Export**, **Configuration and backup**, **Retention**, and **Audit**.
Camera and question selections show saved names and text. Choose an existing rule
to revise it, or choose New rule and leave its ID empty for an automatic ID. Date
pickers use UTC. Export format, timezone, severity, delivery and retention periods
use dropdowns. Filter buttons align with the bottoms of their inputs across the app.

Start VOP selects the live workspace (`--allow-live-sources`). It removes the sample
input and stored test captures, images, alerts, delivery records, rules, presets,
and saved test engines. Test-only source configuration and its audit entries are
removed in the same transaction. Real camera details, protected keys, engine selection,
rules and observations remain. Test answers embedded in real camera history become
timestamp-only gaps, so Trends cannot infer coverage across deleted test results.
The original sample file can no longer recreate test equipment in this workspace.
Backups and files previously exported are separate and are not changed.

Offline tests and explicit development launches without `--allow-live-sources` keep
synthetic fixtures. They remain clearly labelled and do not access cameras or load
models. The live engine editor offers real workers only. A fresh live workspace
uses the approved Antec profile when no real engine has been saved; connection and
GPU recovery still happen only when observation is requested or saved monitoring runs.

### Live images on Observe

Each camera shows two smaller images side by side: **Live view** (or Current image
for a non-live input) and **Last processed image**. Hover over either image, or use
the keyboard to focus its image area, to enlarge it up to the former display size
(800 × 440, limited by the screen). Enlargement does not move the page layout.
Narrow screens stack the pair vertically.

The processed image is the privacy-masked source frame for the latest enabled
question answers. It is published only after the result is stored. A capture or
connection-test preview cannot replace it before new answers exist. Cropped/ROI
questions can use portions of that source frame. New answer text and its processed
image update together; if the image cannot load, VOP hides the old image and shows
a retry message rather than pairing old pixels with new answers.

Completed frames stay in a bounded, temporary per-camera cache even when saved-image
retention is off. Saving images remains a separate setting. After restart or cache
clearing, VOP uses an exactly matching saved frame if available, never an unrelated
older image. Otherwise it explains that a new observation is needed. Missing
capture frames or mixed answer-frame provenance show a message instead of a
misleading picture. Image deletion/retention clears the temporary cache too.

Each camera refreshes independently, so a slow camera does not hold up the other
images. Refreshes do not reload the page or overlap requests for the same camera.
Actual image rate depends on the camera, connection and decoding; 5 fps is a target.
Active and Unknown counters update automatically for the selected cameras, even
when answers are hidden (once per second; open answers check every 0.2 seconds).
Active includes ACTIVE and RECOVERING: an episode remains active until its end is
confirmed. Unknown includes stale, failed and disabled conditions. These counters
use episode states, not an unconfirmed positive answer or the live preview pixels.


Observe shows privacy-masked live previews for configured RTSP and USB cameras,
independently of the interval used to answer questions. A **green ring** and Monitoring
label mean question monitoring is enabled; an **amber ring** and Paused label mean it
is not. Each camera has a **Show images / Hide images** control for the pair. Images start shown
when monitoring is running and hidden when paused. Starting monitoring shows the
image automatically; pausing hides it. You can show or hide it manually in either
state. That choice lasts until the next monitoring change or page reload. Answer
panels stay independent. Showing a paused camera does not start question monitoring.

The preview decoder keeps one camera connection open and continuously drains frames,
publishing only the newest image at a target of 5 frames per second. JPEG previews
are limited to 960 × 540. The visible page checks every 00:00:00.2 and downloads changed
frames only, without reloading the page or closing the answer panels. Each new image
is decoded before replacing the current image; a failed download leaves the last
image visible and retries automatically. Background requests stay on the same VOP
origin. After installing this fix, refresh Observe once to load the updated script.
This is a latency target, not a measured guarantee of camera-to-screen
latency. Camera encoding, network conditions and laptop load still affect it.

Showing an image on Observe starts transient previews with the signed-in
operator's CSRF-protected viewing request; it does not start monitoring, record answers/images or invoke the
engine. Multiple tabs share one decoder per camera. Up to four cameras can have live
previews at once; use the camera filter to view fewer when needed. Hidden images and
hidden/closed tabs stop renewing their viewing lease and connections close within 00:00:15.0 after the
last renewal. Hidden images keep only lightweight monitoring-status checks; image
downloads stop (an in-flight request can finish). Another tab showing the same camera
can keep its shared preview alive. Preview errors retry automatically with bounded backoff; stale images
are labelled as reconnecting rather than presented as current. Viewers still cannot
access image pixels. Endpoints remain authenticated, loopback-only and no-store.

USB previews release exclusive devices during an observation's one-shot acquisition,
then resume. RTSP previews use a separate connection from sampled inference. No
inference sampling rates or saved setup are changed. Other input types keep their
latest captured still image. After restart, saved images can appear while a camera
connects; no frame is invented if nothing is available yet. Recorded-image retention
settings remain independent of these memory-only previews.

Offline process verification: `.\.venv\Scripts\python.exe tools/preview_smoke.py`.
This uses explicit synthetic pixels, requires no camera/OpenCV/model weights, verifies
masks and releases the preview process after its lease expires.


### Answers under each camera

On Observe, each camera has its own **Show answers** button below its controls.
The monitoring control and **Show answers** share one line when space permits; the
answer table opens underneath at full width with compact rows. Open it to see that
camera’s latest answers, **Episode State**, question versions and observation
times; **Hide answers** collapses it. Cameras open independently. Tables are hidden
initially and reset to hidden on page reload. The source filter still limits which
cameras appear. Opening a panel checks for new recorded answers immediately, then every
00:00:00.2 while the panel and page are visible. Only changed table content is replaced;
the panel, picture and page stay in place. Closed panels make no answer requests.
Requests are read-only and do not capture images, invoke the model or change monitoring.
Fresh answers still depend on completion of each scheduled observation; live pictures
update independently. Without JavaScript, Refresh view updates the table.

Each question includes a value bar with a text label and number. Yes/No uses the native
Liquid Yes score where available, otherwise the returned Yes (1.0) or No (0.0) answer.
Ordinal bars use 0 through the last configured level; level names and the numeric answer
remain visible. Choice questions show each option's native score if available, otherwise
which option was selected. Score percentages are model outputs, not calibrated accuracy
or probabilities; hover over a bar for its meaning. Unknown, failed, disabled or stale
answers show **No current value**, rather than a zero bar. Displayed values use one
decimal place; stored values keep full precision.
## Actions and Automations (Phase 5)

**Play audio** supports microphone recording with start/stop, preview and discard. It also
imports MP3, M4A, WAV and other browser-supported clips up to 00:01:00/10 MB, converting them
automatically for playback. Browser microphone permission is requested only after Start
recording. Nothing is stored until Save action. See [audio setup](docs/actions.md#sound-destination).

Configure mode now has **Actions** and **Automations**. Create named beep, WAV audio,
Tapo L530 light, H100 hub sound, SMTP email or Twilio SMS actions; connect them to
confirmed episodes, answer values or observation availability. Use **Preview automation**
before enabling it. **Test action** performs the real action. No destinations or enabled
automations are supplied by default.

View mode **Activity** shows queued, completed, provider-accepted, blocked, uncertain and
expired actions without reloading the page. Browser audio needs **Enable sound**; computer
audio plays on the dashboard computer, independently of Antec inference. Global pause
stops automations while camera monitoring continues. Saved definitions and audio survive
restart; old queued actions are not replayed. Full backup includes the Actions database
extension; OS-protected account details remain in the local vault.

See [Actions setup and limitations](docs/actions.md) and the
[authorised Phase 5 contract](CODEX_PHASE_5_PLAN.md). Tapo support is an optional pinned
installation: `.\.venv\Scripts\python.exe -m pip install ".[tapo]"`.
