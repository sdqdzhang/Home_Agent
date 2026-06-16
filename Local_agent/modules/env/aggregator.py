from __future__ import annotations

from typing import Any


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"avg": None, "max": None, "min": None}
    return {
        "avg": round(sum(values) / len(values), 2),
        "max": round(max(values), 2),
        "min": round(min(values), 2),
    }


def _proxy_vpn_changes(samples: list[dict[str, Any]]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    prev: tuple[bool, bool] | None = None
    for sample in samples:
        net = sample.get("network") or {}
        state = (bool(net.get("proxy_enabled")), bool(net.get("vpn_active")))
        if prev is not None and state != prev:
            ts = sample.get("timestamp_iso", "")
            if state[0] != prev[0]:
                changes.append(
                    {
                        "time": ts,
                        "event": f"Proxy Turned {'ON' if state[0] else 'OFF'}",
                    }
                )
            if state[1] != prev[1]:
                changes.append(
                    {
                        "time": ts,
                        "event": f"VPN Turned {'ON' if state[1] else 'OFF'}",
                    }
                )
        prev = state
    return changes


def _aggregate_top_processes(samples: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    proc_stats: dict[str, dict[str, Any]] = {}
    for sample in samples:
        for proc in sample.get("top_processes") or []:
            key = f"{proc.get('name')}:{proc.get('pid')}"
            if key not in proc_stats:
                proc_stats[key] = {
                    "name": proc.get("name"),
                    "pid": proc.get("pid"),
                    "appearances": 0,
                    "cpu_sum": 0.0,
                    "memory_sum": 0.0,
                }
            proc_stats[key]["appearances"] += 1
            proc_stats[key]["cpu_sum"] += float(proc.get("cpu_percent") or 0)
            proc_stats[key]["memory_sum"] += float(proc.get("memory_percent") or 0)

    ranked = []
    for item in proc_stats.values():
        count = max(item["appearances"], 1)
        ranked.append(
            {
                "name": item["name"],
                "pid": item["pid"],
                "appearances": item["appearances"],
                "cpu_percent_avg": round(item["cpu_sum"] / count, 2),
                "memory_percent_avg": round(item["memory_sum"] / count, 2),
            }
        )
    ranked.sort(key=lambda p: p["cpu_percent_avg"] + p["memory_percent_avg"], reverse=True)
    return ranked[:limit]


def aggregate_samples(samples: list[dict[str, Any]], *, interval_seconds: int = 20) -> dict[str, Any]:
    """将采集窗口内的原始样本压缩为单一 JSON 总结包。"""
    if not samples:
        return {"sample_count": 0, "window_seconds": 0}

    cpu = [float(s["cpu_percent"]) for s in samples]
    mem = [float(s["memory_percent"]) for s in samples]
    upload = [float((s.get("network") or {}).get("upload_mbps") or 0) for s in samples]
    download = [float((s.get("network") or {}).get("download_mbps") or 0) for s in samples]
    latency = [
        float(v)
        for s in samples
        for v in [
            (s.get("network") or {}).get("ping", {}).get("latency_ms"),
        ]
        if v is not None and not (s.get("network") or {}).get("ping", {}).get("skipped")
    ]
    loss = [
        float(v)
        for s in samples
        for v in [
            (s.get("network") or {}).get("ping", {}).get("packet_loss_percent"),
        ]
        if v is not None and not (s.get("network") or {}).get("ping", {}).get("skipped")
    ]
    last_net = samples[-1].get("network") or {}

    return {
        "window_seconds": len(samples) * interval_seconds,
        "sample_count": len(samples),
        "period_start": samples[0].get("timestamp_iso"),
        "period_end": samples[-1].get("timestamp_iso"),
        "cpu_percent": _stats(cpu),
        "memory_percent": _stats(mem),
        "network": {
            "upload_mbps": _stats(upload),
            "download_mbps": _stats(download),
            "ping": {
                "target": (last_net.get("ping") or {}).get("target"),
                "latency_ms": _stats(latency),
                "packet_loss_percent": _stats(loss),
            },
            "proxy_vpn": {
                "proxy_enabled": bool(last_net.get("proxy_enabled")),
                "vpn_active": bool(last_net.get("vpn_active")),
                "changes": _proxy_vpn_changes(samples),
            },
        },
        "disks": samples[-1].get("disks") or [],
        "top_processes": _aggregate_top_processes(samples),
    }
