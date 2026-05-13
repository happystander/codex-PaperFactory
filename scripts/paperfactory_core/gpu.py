"""GPU status helpers for PaperFactory UI and prompts."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from typing import Any

from paperfactory_core import runtime_env


GPU_QUERY = (
    "index,uuid,name,memory.total,memory.used,memory.free,"
    "utilization.gpu,temperature.gpu,power.draw,power.limit"
)
PROCESS_QUERY = "gpu_uuid,pid,process_name,used_memory"


def _int_or_none(value: str) -> int | None:
    text = value.strip()
    if not text or text.upper() == "N/A":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _float_or_none(value: str) -> float | None:
    text = value.strip()
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _run_nvidia_smi(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["nvidia-smi", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )


def _empty_status(*, command_available: bool, health: str, message: str, error: str = "") -> dict[str, Any]:
    return {
        "checked_at": datetime.now().astimezone().isoformat(),
        "command_available": command_available,
        "available": False,
        "health": health,
        "message": message,
        "error": error,
        "gpu_count": 0,
        "idle_count": 0,
        "recommended_gpu_indexes": [],
        "gpus": [],
    }


def _torch_cuda_fallback(timeout: float = 8.0) -> dict[str, Any] | None:
    """Return a coarse CUDA snapshot via torch when NVML/nvidia-smi is unavailable."""

    status = runtime_env.runtime_status()
    python_bin = str(status.get("selected", {}).get("executable") or "")
    if not python_bin:
        return None
    code = r"""
import json
payload = {"available": False, "gpus": [], "error": ""}
try:
    import torch
    payload["available"] = bool(torch.cuda.is_available())
    for index in range(torch.cuda.device_count()):
        free, total = torch.cuda.mem_get_info(index)
        payload["gpus"].append({
            "index": index,
            "name": torch.cuda.get_device_name(index),
            "memory_total_mb": int(total // (1024 * 1024)),
            "memory_free_mb": int(free // (1024 * 1024)),
            "memory_used_mb": int((total - free) // (1024 * 1024)),
        })
except Exception as exc:
    payload["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(payload, ensure_ascii=False))
"""
    try:
        proc = subprocess.run(
            [python_bin, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        return None
    if not payload.get("available") or not payload.get("gpus"):
        return None
    gpus: list[dict[str, Any]] = []
    for item in payload.get("gpus", []):
        total = item.get("memory_total_mb")
        used = item.get("memory_used_mb")
        memory_used_percent = round((used / total) * 100, 1) if used is not None and total else None
        free_ratio = (item.get("memory_free_mb") / total) if item.get("memory_free_mb") is not None and total else 0
        idle = used is None or used <= 512
        usable = idle or free_ratio >= 0.75
        gpus.append(
            {
                "index": item.get("index"),
                "uuid": "",
                "name": item.get("name"),
                "memory_total_mb": total,
                "memory_used_mb": used,
                "memory_free_mb": item.get("memory_free_mb"),
                "memory_used_percent": memory_used_percent,
                "utilization_percent": None,
                "temperature_c": None,
                "power_w": None,
                "power_limit_w": None,
                "process_count": 0,
                "processes": [],
                "status": "idle" if idle else "usable" if usable else "busy",
                "idle": idle,
                "usable": usable,
                "source": "torch",
            }
        )
    recommended = [
        item["index"]
        for item in sorted(gpus, key=lambda gpu: (0 if gpu["status"] == "idle" else 1, -(gpu.get("memory_free_mb") or 0)))
        if item.get("usable") and item.get("index") is not None
    ]
    idle_count = sum(1 for item in gpus if item.get("idle"))
    usable_count = sum(1 for item in gpus if item.get("usable"))
    return {
        "checked_at": datetime.now().astimezone().isoformat(),
        "command_available": shutil.which("nvidia-smi") is not None,
        "available": True,
        "health": "available_torch_fallback",
        "message": f"{usable_count} usable CUDA GPU(s) via torch fallback; nvidia-smi/NVML is unavailable",
        "error": payload.get("error", ""),
        "gpu_count": len(gpus),
        "idle_count": idle_count,
        "usable_count": usable_count,
        "recommended_gpu_indexes": recommended,
        "gpus": gpus,
        "source": "torch",
    }


def gpu_status(timeout: float = 3.0) -> dict[str, Any]:
    """Return a structured snapshot of local NVIDIA GPU availability.

    The helper treats nvidia-smi as optional. Driver failures and missing binaries
    are returned as data so the UI and prompt can explain the state cleanly.
    """

    if shutil.which("nvidia-smi") is None:
        return _empty_status(
            command_available=False,
            health="missing_tool",
            message="nvidia-smi is not on PATH",
        )

    try:
        proc = _run_nvidia_smi(
            [f"--query-gpu={GPU_QUERY}", "--format=csv,noheader,nounits"],
            timeout,
        )
    except subprocess.TimeoutExpired:
        return _empty_status(
            command_available=True,
            health="timeout",
            message="nvidia-smi timed out",
        )
    except OSError as exc:
        return _empty_status(
            command_available=True,
            health="error",
            message="nvidia-smi could not be executed",
            error=str(exc),
        )

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        fallback = _torch_cuda_fallback(timeout=max(timeout, 20.0))
        if fallback:
            fallback["nvidia_smi_error"] = detail
            return fallback
        return _empty_status(
            command_available=True,
            health="driver_unavailable",
            message="nvidia-smi failed; NVIDIA driver or device is unavailable",
            error=detail,
        )

    processes_by_uuid: dict[str, list[dict[str, Any]]] = {}
    try:
        proc_apps = _run_nvidia_smi(
            [f"--query-compute-apps={PROCESS_QUERY}", "--format=csv,noheader,nounits"],
            timeout,
        )
    except (subprocess.TimeoutExpired, OSError):
        proc_apps = None
    if proc_apps is not None and proc_apps.returncode == 0:
        for line in proc_apps.stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 4:
                continue
            uuid, pid, name, used = parts[:4]
            processes_by_uuid.setdefault(uuid, []).append(
                {
                    "pid": _int_or_none(pid),
                    "name": name,
                    "used_memory_mb": _int_or_none(used),
                }
            )

    gpus: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 10:
            continue
        index, uuid, name, total, used, free, util, temp, power, power_limit = parts[:10]
        total_mb = _int_or_none(total)
        used_mb = _int_or_none(used)
        free_mb = _int_or_none(free)
        util_percent = _int_or_none(util)
        memory_used_percent = (
            round((used_mb / total_mb) * 100, 1)
            if used_mb is not None and total_mb
            else None
        )
        free_ratio = (free_mb / total_mb) if free_mb is not None and total_mb else 0.0
        processes = processes_by_uuid.get(uuid, [])
        idle = (
            (used_mb is None or used_mb <= 512)
            and (util_percent is None or util_percent <= 5)
            and not processes
        )
        usable = idle or (
            free_ratio >= 0.75
            and (util_percent is None or util_percent <= 20)
            and len(processes) <= 1
        )
        if idle:
            status = "idle"
        elif usable:
            status = "usable"
        else:
            status = "busy"
        gpus.append(
            {
                "index": _int_or_none(index),
                "uuid": uuid,
                "name": name,
                "memory_total_mb": total_mb,
                "memory_used_mb": used_mb,
                "memory_free_mb": free_mb,
                "memory_used_percent": memory_used_percent,
                "utilization_percent": util_percent,
                "temperature_c": _int_or_none(temp),
                "power_w": _float_or_none(power),
                "power_limit_w": _float_or_none(power_limit),
                "process_count": len(processes),
                "processes": processes[:8],
                "status": status,
                "idle": idle,
                "usable": usable,
            }
        )

    recommended = [
        gpu["index"]
        for gpu in sorted(
            gpus,
            key=lambda item: (
                0 if item["status"] == "idle" else 1 if item["status"] == "usable" else 2,
                -(item.get("memory_free_mb") or 0),
                item.get("utilization_percent") or 0,
            ),
        )
        if gpu.get("usable") and gpu.get("index") is not None
    ]
    idle_count = sum(1 for gpu in gpus if gpu.get("idle"))
    usable_count = sum(1 for gpu in gpus if gpu.get("usable"))
    if not gpus:
        health = "empty"
        message = "nvidia-smi returned no GPU rows"
    elif usable_count:
        health = "available"
        message = f"{usable_count} usable GPU(s), {idle_count} idle"
    else:
        health = "busy"
        message = "No idle or lightly loaded GPU found"
    return {
        "checked_at": datetime.now().astimezone().isoformat(),
        "command_available": True,
        "available": True,
        "health": health,
        "message": message,
        "error": "",
        "gpu_count": len(gpus),
        "idle_count": idle_count,
        "usable_count": usable_count,
        "recommended_gpu_indexes": recommended,
        "gpus": gpus,
    }


def gpu_prompt_context(status: dict[str, Any] | None = None) -> str:
    """Format GPU state for injection into Codex phase prompts."""

    snapshot = status or gpu_status()
    lines = ["GPU resource snapshot:"]
    lines.append(f"- Checked at: {snapshot.get('checked_at') or 'unknown'}")
    if not snapshot.get("command_available"):
        lines.append("- nvidia-smi: not found on PATH.")
        lines.append("- Guidance: do not assume GPU access; use CPU-only diagnostics unless the phase explicitly waits for GPU.")
        return "\n".join(lines)
    if not snapshot.get("available"):
        lines.append(f"- nvidia-smi: unavailable ({snapshot.get('message') or 'unknown error'}).")
        error = str(snapshot.get("error") or "").splitlines()[0:2]
        if error:
            lines.append(f"- Error: {' / '.join(error)}")
        lines.append("- Guidance: do not launch GPU training. If GPU work is required, monitor availability or mark the GPU dependency as blocked according to the user instruction.")
        return "\n".join(lines)
    recommended = snapshot.get("recommended_gpu_indexes") or []
    lines.append(
        f"- GPUs: {snapshot.get('gpu_count', 0)} total, {snapshot.get('idle_count', 0)} idle, "
        f"{snapshot.get('usable_count', 0)} usable."
    )
    lines.append(f"- Recommended GPU indexes: {recommended if recommended else 'none'}")
    for gpu in snapshot.get("gpus", [])[:12]:
        lines.append(
            "- GPU {index}: {status}, {name}, free {free}/{total} MiB, util {util}%, temp {temp}C, processes {proc}".format(
                index=gpu.get("index"),
                status=gpu.get("status"),
                name=gpu.get("name"),
                free=gpu.get("memory_free_mb"),
                total=gpu.get("memory_total_mb"),
                util=gpu.get("utilization_percent"),
                temp=gpu.get("temperature_c"),
                proc=gpu.get("process_count"),
            )
        )
    lines.append("- Guidance: before any GPU experiment, re-check nvidia-smi, select an idle/usable GPU, set CUDA_VISIBLE_DEVICES explicitly, and record the GPU index in experiment artifacts.")
    return "\n".join(lines)
