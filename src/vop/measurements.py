"""Pure temporal replay over immutable observations; gaps never assert a negative."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import math
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def timezone_for(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("Unknown timezone") from exc


def utc(value: str | datetime) -> datetime:
    stamp = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return stamp.astimezone(timezone.utc)


def rectangle(value) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4 or any(isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) for n in value):
        raise ValueError("ROI must be four finite numbers: x, y, width, height")
    x, y, width, height = value
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise ValueError("ROI must lie inside the normalised image bounds")
    return tuple(float(v) for v in value)


@dataclass(frozen=True)
class QueryPolicy:
    positive_confirmations: int = 2
    negative_confirmations: int = 2
    max_gap_seconds: float = 60
    unknown_gap_policy: str = "resume"
    roi: tuple[float, float, float, float] | None = None

    def __post_init__(self):
        if any(type(n) is not int or not 1 <= n <= 100 for n in (self.positive_confirmations, self.negative_confirmations)):
            raise ValueError("Confirmations must be integers in [1, 100]")
        if isinstance(self.max_gap_seconds, bool) or not math.isfinite(self.max_gap_seconds) or not 1 <= self.max_gap_seconds <= 86400:
            raise ValueError("Maximum gap must be in [1, 86400] seconds")
        if self.unknown_gap_policy not in ("resume", "split", "manual_review"):
            raise ValueError("Gap policy must be resume, split or manual_review")
        object.__setattr__(self, "roi", rectangle(self.roi))


def replay(observations: list[dict], policy: QueryPolicy, *, kind: str = "binary",
           as_of: str | datetime | None = None, timezone_name: str = "UTC",
           range_start=None, range_end=None) -> dict:
    """Ordered stream semantics; materialised events use stable observation-derived IDs.

    Durations interpolate only bounded intervals whose endpoints were successfully sampled.
    They are estimates, not proof of continuous visibility. No extrapolated active duration.
    """
    zone = timezone_for(timezone_name)
    state, positive, negative = "UNKNOWN", 0, 0
    events, trend, categories, buckets = [], [], {}, {}
    active = None
    last_time = None
    last_valid = False
    last_value = None
    coverage = unknown = duration = 0.0
    samples = valid_samples = 0
    last_observation_id = None
    last_good_time = None
    review_required = False
    covered_intervals, unknown_intervals, sampled_points = [], [], []
    for row in observations:
        if not row.get("temporal_eligible", True):
            continue
        stamp = utc(row.get("captured_at_utc") or row["processed_at_utc"])
        if last_time is not None and stamp < last_time:
            continue
        answer = row["answer"]
        value = answer.get("value")
        valid = row["status"] == "success" and value is not None
        if kind == "binary" and not isinstance(value, bool):
            valid = False
        previous_state = state
        gap = False
        if last_time is not None:
            elapsed = (stamp - last_time).total_seconds()
            covered = last_valid and valid and elapsed <= policy.max_gap_seconds and not review_required
            if covered:
                coverage += elapsed
                covered_intervals.append((last_time, stamp, last_value))
                if kind == "choice":
                    categories[str(last_value)] = categories.get(str(last_value), 0) + elapsed
                if active is not None and previous_state in ("ACTIVE", "RECOVERING"):
                    events[active]["estimated_observed_seconds"] += elapsed
                    events[active]["segments"].append({"from": last_time.isoformat(), "to": stamp.isoformat()})
                    duration += elapsed
            else:
                unknown += elapsed
                unknown_intervals.append((last_time, stamp))
                gap = True
                if active is not None:
                    events[active]["unknown_seconds"] += elapsed
                    events[active]["unknown_intervals"].append({"from": last_time.isoformat(), "to": stamp.isoformat()})
                    if policy.unknown_gap_policy == "split":
                        events[active]["status"] = "interrupted"
                        events[active]["interrupted_at_utc"] = last_time.isoformat()
                        active = None
                    elif policy.unknown_gap_policy == "manual_review":
                        review_required = True
                state, positive, negative = "UNKNOWN", 0, 0
        if review_required:
            state, positive, negative = "UNKNOWN", 0, 0
        elif not valid:
            state, positive, negative = "UNKNOWN", 0, 0
        elif kind == "binary":
            if value is True:
                negative = 0
                if active is not None and not gap and previous_state in ("ACTIVE", "RECOVERING"):
                    state, positive = "ACTIVE", policy.positive_confirmations
                else:
                    positive += 1
                    state = "PENDING"
                    if positive >= policy.positive_confirmations:
                        state = "ACTIVE"
                        if active is None:
                            event_id = sha256(f"{row['source_id']}:{row['question_id']}:{row['question_version']}:{row['id']}".encode()).hexdigest()[:32]
                            events.append({"id": event_id, "source_id": row["source_id"], "question_id": row["question_id"],
                                           "question_version": row["question_version"], "started_at_utc": stamp.isoformat(),
                                           "ended_at_utc": None, "start_observation_id": row["id"], "end_observation_id": None,
                                           "status": "open", "estimated_observed_seconds": 0.0, "unknown_seconds": 0.0,
                                           "segments": [], "unknown_intervals": []})
                            active = len(events) - 1
                            day = stamp.astimezone(zone).date().isoformat()
                            buckets[day] = buckets.get(day, 0) + 1
            elif value is False:
                positive = 0
                if active is not None:
                    negative += 1
                    state = "RECOVERING"
                    if negative >= policy.negative_confirmations:
                        state = "INACTIVE"
                        events[active].update(status="closed", ended_at_utc=stamp.isoformat(), end_observation_id=row["id"])
                        active = None
                else:
                    state, negative = "INACTIVE", 0
            else:
                state, positive, negative = "UNKNOWN", 0, 0
        else:
            state = "OBSERVED"
        samples += int(not row.get('retention_gap'))
        valid_samples += int(valid)
        if not row.get('retention_gap'):
            sampled_points.append((stamp, valid))
        if valid and kind == "binary":
            buckets.setdefault(stamp.astimezone(zone).date().isoformat(), 0)
        trend.append({"at_utc": stamp.isoformat(), "local_label": stamp.astimezone(zone).strftime("%d %b %H:%M:%S %Z %z"), "gap_before": gap,
                      "value": value if valid else None})
        last_time, last_valid, last_value, last_observation_id = stamp, valid, value, None if row.get('retention_gap') else row["id"]
        if valid:
            last_good_time = stamp
    stale = False
    if as_of is not None and last_time is not None:
        elapsed = (utc(as_of) - last_time).total_seconds()
        if elapsed > policy.max_gap_seconds:
            state, stale = "UNKNOWN", True
            unknown += max(0, elapsed)
            unknown_intervals.append((last_time, utc(as_of)))
    window_start = utc(range_start) if range_start is not None else None
    window_end = utc(range_end) if range_end is not None else None
    if window_start and window_end and window_end <= window_start:
        raise ValueError("Metric range end must follow its start")
    def in_window(stamp):
        return (window_start is None or stamp >= window_start) and (window_end is None or stamp < window_end)
    def clipped(start, end):
        if window_start:
            start = max(start, window_start)
        if window_end:
            end = min(end, window_end)
        return max(0, (end - start).total_seconds())
    episode_count = len(events) if valid_samples else None
    if window_start is not None or window_end is not None:
        coverage = sum(clipped(a, b) for a, b, value in covered_intervals)
        unknown = sum(clipped(a, b) for a, b in unknown_intervals)
        duration = sum(clipped(utc(segment["from"]), utc(segment["to"])) for event in events for segment in event["segments"])
        categories = {}
        if kind == "choice":
            for a, b, value in covered_intervals:
                if clipped(a, b):
                    categories[str(value)] = categories.get(str(value), 0) + clipped(a, b)
        samples = sum(in_window(stamp) for stamp, valid in sampled_points)
        valid_samples = sum(in_window(stamp) and valid for stamp, valid in sampled_points)
        episode_count = sum(in_window(utc(event["started_at_utc"])) for event in events) if valid_samples or coverage > 0 else None
        trend = [point for point in trend if in_window(utc(point["at_utc"]))]
        buckets = {stamp.astimezone(zone).date().isoformat(): 0 for stamp, valid in sampled_points if valid and in_window(stamp) and kind == "binary"}
        for event in events:
            stamp = utc(event["started_at_utc"])
            if in_window(stamp):
                day = stamp.astimezone(zone).date().isoformat()
                buckets[day] = buckets.get(day, 0) + 1
    span = coverage + unknown
    return {"state": state, "stale": stale, "review_required": review_required, "latest_value": last_value if last_valid and not stale else None,
            "last_observation_id": last_observation_id, "last_observed_at_utc": last_good_time.isoformat() if last_good_time else None,
            "last_sample_at_utc": last_time.isoformat() if last_time else None,
            "sample_count": samples, "valid_sample_count": valid_samples,
            "episode_count": episode_count, "events": events,
            "estimated_active_seconds": duration, "covered_seconds": coverage, "unknown_seconds": unknown,
            "coverage_fraction": coverage / span if span > 0 else None,
            "occupancy_fraction": duration / coverage if coverage > 0 and kind == "binary" else None,
            "episodes_per_hour": episode_count * 3600 / coverage if episode_count is not None and coverage > 0 and kind == "binary" else None,
            "daily_episode_counts": buckets, "choice_dwell_seconds": categories, "trend": trend}
