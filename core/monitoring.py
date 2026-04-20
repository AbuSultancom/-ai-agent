"""Monitoring — track token usage, costs, latency, and request counts."""

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

_lock = threading.Lock()

# claude-opus-4-7 pricing per million tokens (as of 2024)
_PRICING = {
    "input": 15.0,
    "output": 75.0,
    "cache_write": 18.75,
    "cache_read": 1.50,
}

_stats = {
    "total_requests": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cache_write_tokens": 0,
    "total_cache_read_tokens": 0,
    "total_cost_usd": 0.0,
    "errors": 0,
    "started_at": datetime.now(timezone.utc).isoformat(),
}

_request_log: deque = deque(maxlen=500)
_latency_by_endpoint: dict = defaultdict(list)


def record_request(
    endpoint: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_write: int = 0,
    cache_read: int = 0,
    latency_ms: float = 0.0,
    error: bool = False,
) -> None:
    cost = (
        input_tokens * _PRICING["input"]
        + output_tokens * _PRICING["output"]
        + cache_write * _PRICING["cache_write"]
        + cache_read * _PRICING["cache_read"]
    ) / 1_000_000

    with _lock:
        _stats["total_requests"] += 1
        _stats["total_input_tokens"] += input_tokens
        _stats["total_output_tokens"] += output_tokens
        _stats["total_cache_write_tokens"] += cache_write
        _stats["total_cache_read_tokens"] += cache_read
        _stats["total_cost_usd"] += cost
        if error:
            _stats["errors"] += 1

        _request_log.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "latency_ms": round(latency_ms),
            "error": error,
        })
        _latency_by_endpoint[endpoint].append(latency_ms)


def get_stats() -> dict:
    with _lock:
        stats = dict(_stats)
        avg_latency = {}
        for ep, latencies in _latency_by_endpoint.items():
            if latencies:
                avg_latency[ep] = round(sum(latencies) / len(latencies))
        stats["avg_latency_ms_by_endpoint"] = avg_latency
        stats["total_cost_usd"] = round(stats["total_cost_usd"], 4)
        return stats


def get_recent_requests(n: int = 50) -> list:
    with _lock:
        return list(_request_log)[-n:]


def get_hourly_summary() -> list:
    with _lock:
        logs = list(_request_log)

    hourly: dict = defaultdict(lambda: {"requests": 0, "tokens": 0, "cost": 0.0, "errors": 0})
    for entry in logs:
        hour = entry["ts"][:13]  # "2024-01-01T12"
        hourly[hour]["requests"] += 1
        hourly[hour]["tokens"] += entry["input_tokens"] + entry["output_tokens"]
        hourly[hour]["cost"] += entry["cost_usd"]
        if entry["error"]:
            hourly[hour]["errors"] += 1

    return [{"hour": h, **v} for h, v in sorted(hourly.items())]
