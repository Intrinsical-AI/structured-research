"""Compute minimal Q2 operational metrics from structured JSONL metric events."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

METRICS_LOG_PATH = Path("runs/metrics_q2_events.jsonl")

TARGETS = {
    "run_latency_p95_ms": 1500.0,
    "snapshot_failed_rate": 0.01,
    "jsonl_parse_error_ratio": 0.15,
    "gen_cv_fallback_used_ratio": 0.20,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metrics-log",
        default=str(METRICS_LOG_PATH),
        help="Path to metrics JSONL file",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window in days (default: 7)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output instead of text table",
    )
    return parser.parse_args(argv)


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * weight


def _load_events(path: Path, since: datetime) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            recorded_at = payload.get("recorded_at")
            if not isinstance(recorded_at, str):
                continue
            ts = _parse_ts(recorded_at)
            if ts is None:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if ts >= since:
                events.append(payload)
    return events


def _avg(values: Iterable[float]) -> float | None:
    items = list(values)
    if not items:
        return None
    return sum(items) / len(items)


def _ratio(part: float, total: float) -> float | None:
    if total <= 0:
        return None
    return part / total


def compute_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    run_events = [e for e in events if e.get("event_type") == "job_search_run"]
    validate_events = [e for e in events if e.get("event_type") == "job_search_jsonl_validate"]
    gen_cv_events = [e for e in events if e.get("event_type") == "gen_cv"]

    latencies = [
        float(e["latency_ms"]) for e in run_events if isinstance(e.get("latency_ms"), (int, float))
    ]
    run_latency_p95 = _percentile(latencies, 0.95)

    snapshot_failed = sum(1 for e in run_events if e.get("snapshot_status") == "failed")
    snapshot_failed_rate = _ratio(snapshot_failed, len(run_events))

    total_lines = sum(
        int(e["total_lines"]) for e in validate_events if isinstance(e.get("total_lines"), int)
    )
    parse_errors = sum(
        int(e["parse_errors"]) for e in validate_events if isinstance(e.get("parse_errors"), int)
    )
    jsonl_parse_error_ratio = _ratio(parse_errors, total_lines)

    parse_ratios = [
        float(e["parse_error_ratio"])
        for e in validate_events
        if isinstance(e.get("parse_error_ratio"), (int, float))
    ]
    jsonl_parse_error_ratio_median = median(parse_ratios) if parse_ratios else None

    fallback_used = sum(1 for e in gen_cv_events if bool(e.get("fallback_used")))
    gen_cv_fallback_used_ratio = _ratio(fallback_used, len(gen_cv_events))

    return {
        "counts": {
            "events_total": len(events),
            "run_events": len(run_events),
            "jsonl_validate_events": len(validate_events),
            "gen_cv_events": len(gen_cv_events),
        },
        "metrics": {
            "run_latency_p95_ms": run_latency_p95,
            "run_latency_avg_ms": _avg(latencies),
            "snapshot_failed_rate": snapshot_failed_rate,
            "jsonl_parse_error_ratio": jsonl_parse_error_ratio,
            "jsonl_parse_error_ratio_median": jsonl_parse_error_ratio_median,
            "gen_cv_fallback_used_ratio": gen_cv_fallback_used_ratio,
        },
        "targets": TARGETS,
    }


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _status(metric: str, value: float | None) -> str:
    target = TARGETS[metric]
    if value is None:
        return "NO_DATA"
    return "PASS" if value <= target else "FAIL"


def print_text_report(report: dict[str, Any], *, log_path: Path, days: int) -> None:
    counts = report["counts"]
    metrics = report["metrics"]

    print(f"Q2 metrics report (last {days}d)")
    print(f"source={log_path}")
    print(
        "events: total={events_total}, run={run_events}, jsonl_validate={jsonl_validate_events}, gen_cv={gen_cv_events}".format(
            **counts
        )
    )
    print("")
    print("metric                           value       target      status")
    print("---------------------------------------------------------------")
    print(
        f"run_latency_p95_ms                {_fmt_ms(metrics['run_latency_p95_ms']):>8}    <= {TARGETS['run_latency_p95_ms']:.0f}ms   {_status('run_latency_p95_ms', metrics['run_latency_p95_ms'])}"
    )
    print(
        f"snapshot_failed_rate              {_fmt_pct(metrics['snapshot_failed_rate']):>8}    <  {TARGETS['snapshot_failed_rate'] * 100:.2f}%   {_status('snapshot_failed_rate', metrics['snapshot_failed_rate'])}"
    )
    print(
        f"jsonl_parse_error_ratio           {_fmt_pct(metrics['jsonl_parse_error_ratio']):>8}    <  {TARGETS['jsonl_parse_error_ratio'] * 100:.2f}%   {_status('jsonl_parse_error_ratio', metrics['jsonl_parse_error_ratio'])}"
    )
    print(
        f"gen_cv_fallback_used_ratio        {_fmt_pct(metrics['gen_cv_fallback_used_ratio']):>8}    <  {TARGETS['gen_cv_fallback_used_ratio'] * 100:.2f}%   {_status('gen_cv_fallback_used_ratio', metrics['gen_cv_fallback_used_ratio'])}"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_path = Path(args.metrics_log)
    since = datetime.now(UTC) - timedelta(days=args.days)
    report = compute_report(_load_events(log_path, since))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_text_report(report, log_path=log_path, days=args.days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
