"""Network and proxy diagnostics for autonomous research runs."""

from __future__ import annotations

import os
import socket
import urllib.parse
from datetime import datetime
from typing import Any


PROXY_KEYS = ("https_proxy", "http_proxy", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "ALL_PROXY")


def _proxy_reachable(url: str, timeout: float = 1.0) -> bool | None:
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname or not parsed.port:
        return None
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return None
    try:
        with socket.create_connection((parsed.hostname, int(parsed.port)), timeout=timeout):
            return True
    except OSError:
        return False


def network_status() -> dict[str, Any]:
    proxies = {key: os.environ.get(key) for key in PROXY_KEYS if os.environ.get(key)}
    local_checks = {
        key: _proxy_reachable(value)
        for key, value in proxies.items()
        if isinstance(value, str)
    }
    local_proxy_blocked = any(value is False for value in local_checks.values())
    return {
        "checked_at": datetime.now().astimezone().isoformat(),
        "proxies": proxies,
        "local_proxy_checks": local_checks,
        "local_proxy_blocked": local_proxy_blocked,
    }


def prompt_context(status: dict[str, Any] | None = None) -> str:
    snapshot = status or network_status()
    proxies = snapshot.get("proxies", {})
    lines = ["Network/proxy snapshot:"]
    if not proxies:
        lines.append("- Proxy env: none detected.")
    else:
        display = [f"{key}={value}" for key, value in proxies.items()]
        lines.append(f"- Proxy env: {'; '.join(display)}")
    checks = snapshot.get("local_proxy_checks", {})
    blocked = [key for key, value in checks.items() if value is False]
    reachable = [key for key, value in checks.items() if value is True]
    if reachable:
        lines.append(f"- Local proxy reachable from this process: {reachable}")
    if blocked:
        lines.append(f"- Local proxy not reachable from this process: {blocked}")
    lines.append("- Guidance: for downloads, prefer robust helpers with retries, checksums, shallow clones, and explicit fallbacks to release archives or raw files.")
    lines.append("- If a Codex sandbox cannot reach a localhost proxy or GPU devices, use PaperFactory host-access mode for experiment cycles and record that mode in the run log.")
    return "\n".join(lines)
