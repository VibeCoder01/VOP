# Phase 2 — browser MVP capability

Owner authorisation: 13 October 2026 after the owner ran the Phase 1 laptop smoke successfully.
Phase 1 PR #2 remains unmerged at commencement: develop on `codex/phase-2` based on that
tested branch, with a separate stacked PR; do not merge either automatically.

Scope: SRS §15 Phase 2 — question editor, temporal state machine, event metrics, opt-in evidence,
dashboard and disconnect handling. Keep existing byte-oriented inference and explicit live/model
consent. Real camera/accuracy/GPU results require real execution and separate reporting.

| Gate | Software acceptance |
|---|---|
| P2-01 | Browser operator/viewer login, CSRF-protected writes, logout, escaped inputs; API bearer access preserved. |
| P2-02 | Source status/control and question editor supporting binary/choice/ordinal, immutable revisions, thresholds, confirmations, gaps and optional ROI. |
| P2-03 | Replay-deterministic INACTIVE/PENDING/ACTIVE/RECOVERING/UNKNOWN states; confirmation-based episodes; unknown gaps never produce negative closure. |
| P2-04 | Counts, sampled estimated durations, rate, occupancy/coverage, choice dwell and ordinal trends; zero vs no data; UTC data with timezone/DST labels. |
| P2-05 | Default-off evidence retention, authorised viewing/deletion, viewer denial and privacy-safe deletion; no real imagery committed. |
| P2-06 | Responsive overview/sources/questions/events/metrics views with observation/raw provenance and mock labels; browser interactions work locally/offline. |
| P2-07 | Explicit sampling controls run independently of browser, zero backlog, overload visibility, stale/disconnected state, source retry and disabled-source handling. |
| P2-08 | SQLite v1→v2 migration with backup, restart persistence, query history and deterministic explicit replay; late frames audited without rewriting live events. |
| P2-09 | Offline regression/API/replay/migration/permission/DST tests, actual browser QA and Windows/Linux CI; hardware-dependent AT-01/02 statuses remain honest. |

Trace P2 gates to AT-01–AT-10 in the validation report. Do not equate adapter simulations with
actual USB/Tapo/model accuracy tests. If authorised camera hardware is unavailable, report that
hardware acceptance as pending, with the implemented software path verified on fixtures.
No Phase 3 alert rules/transports, installer, production service deployment, new model format,
GPU inference or remote worker network protocol. Application licence remains undecided.

UI thesis: a calm slate-and-white observation workspace with one teal action accent, readable
tables, clear provenance and prominent UNKNOWN/mock distinctions. Content: source overview,
latest states, recent events, metrics, question/source controls. Interactions: short view entrance,
table/button focus and hover feedback, progressive native forms; respect reduced motion.
FastHTML renders the HTML/SVG. No SPA, frontend build chain or external CDN is required.
