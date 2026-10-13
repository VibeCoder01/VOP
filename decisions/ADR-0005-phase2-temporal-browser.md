# ADR-0005 — replayed temporal capability and local browser workspace

Date: 13 October 2026. Status: proposed for Phase 2 review.

The owner authorised Phase 2 after running the laptop Phase 1 smoke successfully, and separately
authorised brief local USB capture. PR #2 remains unmerged at commencement; the new branch/PR
is stacked on the tested Phase 1 implementation, without automatic merging.

Keep FastHTML native forms, local CSS/SVG and stdlib SQLite. Add signed one-hour browser sessions,
CSRF, a local operator/viewer distinction and bearer API compatibility. No external assets, SPA,
account framework or remote transport is necessary for this capability phase.

Use pure deterministic replay to derive binary states and stable observation-based episodes.
Activation/end use confirmation timestamps. Unknown intervals remain explicit; errors never
become negative closure. Resume/split/manual-review policies are versioned alongside immutable
questions. Choice dwell and ordinal trends keep their own semantics. Metrics use bounded sampled
intervals, UTC arithmetic, local-calendar labels and explicit coverage; not continuous truth.

Schema v2 backs up/upgrades v1 without rewriting historical question specifications. Source
controls, query policies, mock presets and events persist. Revisions supersede old open episodes
without pretending a confirmed end. Late samples remain auditable but cannot rewrite live events.
Replay is O(n) per question for the sparse prototype; incremental state snapshots are warranted
if actual history volume demands them. This is not a scale/capacity claim.

Privacy masks precede ROI and evidence. Retention defaults off; one bounded in-memory preview
supports inspection. Opt-in retained PNGs are operator-only and can be deleted; viewers see no
images. External backup/user copies require their own retention control. No real images are committed.

Sampling starts only through explicit controls, has one worker/zero backlog, and respects live-source
consent. Real model injection still has a synchronous soft deadline; hard model isolation/remote
workers remain later INF-011 work. Default service remains clearly labelled mock inference.

The Dell USB hardware captured 640×480 frames; its capture→mock→persistence→dashboard check passed,
without retained pixels. No new d1-3B/GPU or RTSP camera accuracy result exists. Phase 2 software is
ready for review; hardware/model acceptance remains conditional where untested. Stop before Phase 3.
