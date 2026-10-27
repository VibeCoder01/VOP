# Phase 5 — Actions and Automations

Authorised by the product owner on 27 October 2026: “Excellent, Good plan. Please proceed with implementation.”

Scope: named beep/audio/Tapo light/email/SMS actions; separate Configure pages for Actions
and Automations; an Activity page in View; confirmed episode start/duration/end, answer
value and availability transitions; cooldown, daily schedule, hourly limits, pause,
simulation preview and explicit real-action tests. The first light target is Tapo L530;
the owner's subsequent scope addition includes built-in sound playback on the H100 hub.

Traceability: SRS EVT-003–006, EVT-008, EVT-010; section 9.4 notification/action interface;
NFR-011 accessibility; existing temporal UNKNOWN semantics and deployment neutrality.

Implementation must reuse authentication, CSRF, protected secrets and the existing store.
Action execution is separate from capture, inference and measurement, using a durable
queue. Stable keys prevent repeated polling from producing repeated actions. Jobs expire
and restart must not replay old actions. A provider acceptance is distinct from delivery.
An ambiguous send must not be retried automatically. No default destinations or enabled
automations are created. No real light, email, SMS or audio test without explicit user action.

Exit criteria: offline tests cover persistence, transition deduplication, UNKNOWN,
cooldown/limits/schedule, pause/restart, browser claims, deletion/configuration changes,
adapter contracts and protected setup. Windows and Ubuntu CI must pass. Manual L530,
mail/SMS and audio acceptance remain labelled unverified until deliberately tested.

Phase 6 and arbitrary scripts/plugins are outside this authorisation. Do not auto-merge.
