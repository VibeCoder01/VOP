from datetime import datetime, timedelta, timezone

import pytest

from vop.measurements import QueryPolicy, replay


def rows(values, *, times=None):
    origin = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
    result = []
    for i, value in enumerate(values):
        stamp = origin + timedelta(seconds=times[i] if times else 10 * i)
        result.append({"id": f"obs-{i}", "source_id": "source", "question_id": "question", "question_version": "1",
                       "captured_at_utc": stamp.isoformat() if value is not None else None,
                       "processed_at_utc": stamp.isoformat(), "status": "success" if value is not None else "model_failure",
                       "answer": {"value": value}})
    return result


def test_confirmations_single_episode_and_closure():
    data = rows([False, True, True, True, False, False])
    summary = replay(data, QueryPolicy())
    assert summary["state"] == "INACTIVE" and summary["episode_count"] == 1
    event = summary["events"][0]
    assert event["started_at_utc"] == data[2]["captured_at_utc"]
    assert event["ended_at_utc"] == data[5]["captured_at_utc"] and event["status"] == "closed"
    assert event["estimated_observed_seconds"] == 30
    assert summary == replay(data, QueryPolicy())


def test_unknown_never_closes_episode_and_resume_no_double_count():
    data = rows([True, True, None])
    summary = replay(data, QueryPolicy())
    assert summary["state"] == "UNKNOWN" and summary["events"][0]["ended_at_utc"] is None
    assert summary["events"][0]["unknown_seconds"] == 10
    resumed = replay(rows([True, True, None, True, True, False, False]), QueryPolicy())
    assert resumed["episode_count"] == 1 and resumed["events"][0]["status"] == "closed"
    assert resumed["unknown_seconds"] == 20


def test_gap_split_is_interrupted_not_negative_close():
    summary = replay(rows([True, True, None, True, True]), QueryPolicy(unknown_gap_policy="split"))
    assert summary["episode_count"] == 2
    assert summary["events"][0]["status"] == "interrupted" and summary["events"][0]["ended_at_utc"] is None


def test_stale_and_late_data_no_false_negative():
    data = rows([True, True, False], times=[0, 10, 5])
    summary = replay(data, QueryPolicy(), as_of="2026-10-13T12:02:00+00:00")
    assert summary["state"] == "UNKNOWN" and summary["stale"] and summary["latest_value"] is None
    assert summary["events"][0]["ended_at_utc"] is None


def test_zero_vs_missing_and_choice_dwell():
    assert replay([], QueryPolicy())["episode_count"] is None
    assert replay(rows([False, False]), QueryPolicy())["episode_count"] == 0
    summary = replay(rows(["red", "red", None, "green", "green"]), QueryPolicy(), kind="choice")
    assert summary["choice_dwell_seconds"] == {"red": 10, "green": 10}
    assert summary["unknown_seconds"] == 20
    trend = replay(rows([0.5, None, 1.7]), QueryPolicy(), kind="ordinal")["trend"]
    assert [p["value"] for p in trend] == [0.5, None, 1.7]


def test_dst_labels_keep_utc_instants_distinct():
    data = rows([False, False])
    for row, stamp in zip(data, ["2026-10-25T00:30:00+00:00", "2026-10-25T01:30:00+00:00"]):
        row["captured_at_utc"] = row["processed_at_utc"] = stamp
    summary = replay(data, QueryPolicy(max_gap_seconds=7200), timezone_name="Europe/London")
    labels = [p["local_label"] for p in summary["trend"]]
    assert "01:30:00 BST +0100" in labels[0] and "01:30:00 GMT +0000" in labels[1]
    assert summary["covered_seconds"] == 3600


@pytest.mark.parametrize("kwargs", [{"positive_confirmations": True}, {"negative_confirmations": 0},
                                   {"max_gap_seconds": float("nan")}, {"unknown_gap_policy": "false"},
                                   {"roi": [0.9, 0.9, 0.5, 0.5]}])
def test_invalid_policy(kwargs):
    with pytest.raises(ValueError):
        QueryPolicy(**kwargs)


def test_manual_review_keeps_unknown_and_does_not_close_on_negative():
    summary = replay(rows([True, True, None, False, False]), QueryPolicy(unknown_gap_policy="manual_review"))
    assert summary["state"] == "UNKNOWN" and summary["review_required"]
    assert summary["events"][0]["ended_at_utc"] is None
