# Phase 3 — reliable release

Owner authorisation: 13 October 2026, “That all looks good. Proceed with the next phase.”
Scope follows SRS §15 Phase 3, with Phase 2 accepted by the owner. Remote inference was
suggested in conversation, but the roadmap assigns this phase to reliable-release work;
it is not silently substituted for the specification. No remote worker/GPU/new model
format, production surveillance deployment or Phase 4 work. Keep application licence undecided.

| Gate | Acceptance |
|---|---|
| P3-01 | Duration/count rules and separate source-offline/processing-degraded conditions; immutable audited revisions and provenance. EVT-003, EVT-008. |
| P3-02 | Stable alert keys, durable dashboard notification, operator acknowledge/resolve/notes; UNKNOWN suspends detection re-arming. EVT-004–006, AT-11. |
| P3-03 | Explicit optional HTTPS webhook with host allow-list, no redirects/proxies, stable Idempotency-Key, bounded five-attempt retries and visible failure; simulated sink failures in offline tests. EVT-006–007, AT-11–12. |
| P3-04 | Filtered CSV/JSON event/metric/alert export including provenance/timezone; formula injection protection; no imagery/secret values in tabular exports. UI-007–008, INP-011. |
| P3-05 | Validated versioned configuration export/import and consistent SQLite backup/restoration into a new directory; corrupted/unsafe input rejected; migration backup. QRY-010, OPS-004–005, OPS-008. |
| P3-06 | Preview/apply evidence/raw-detail/audit retention; default no policy; applied policy enforced hourly; normalized history retained for replay, backups operator-managed. OPS-007. |
| P3-07 | Wheel + Windows development installer ZIP built from allow-listed files; fresh install smoke, locked dependencies, rollback guide. OPS-006. |
| P3-08 | Auth/CSRF/viewer/Host/origin/XSS/CSV/endpoint/rate-limit/security regression checks, actual browser and HTTP smoke, Windows/Linux CI evidence. NFR-016, AT-12. |

The phase produces a reviewable development release. A full MVP production sign-off still
requires actual supported RTSP hardware and workload accuracy validation (AT-01/02), licence
review, production secret protection and deployment hardening. Historical d1-3B CPU evidence
on antec is not a new Phase 3 inference run. Never report unexecuted hardware gates as passed.
Alert webhooks are at-least-once delivery: the receiver must deduplicate the stable key after
an ambiguous connection/crash. Advisory sampled duration never asserts continuous visibility.
