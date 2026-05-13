"""Runtime environment discovery for PaperFactory runs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_RESEARCH_MODULES = ("torch", "transformers", "datasets", "hydra", "omegaconf")
PREFERRED_PYTHONS = (
    "/home/lyq/anaconda3/envs/verl_061/bin/python",
)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def candidate_pythons() -> list[str]:
    """Return candidate Python executables, ordered by likely research usefulness."""

    candidates: list[str] = []
    env_python = os.environ.get("PAPERFACTORY_PYTHON") or os.environ.get("PYTHON_BIN")
    if env_python:
        candidates.append(env_python)
    candidates.extend(PREFERRED_PYTHONS)
    candidates.append(sys.executable)
    python3 = shutil.which("python3")
    python = shutil.which("python")
    if python3:
        candidates.append(python3)
    if python:
        candidates.append(python)
    conda_root = Path.home() / "anaconda3" / "envs"
    if conda_root.exists():
        for item in sorted(conda_root.glob("*/bin/python")):
            candidates.append(str(item))
    return [item for item in _dedupe(candidates) if Path(item).exists()]


def inspect_python(python_bin: str, timeout: float = 8.0) -> dict[str, Any]:
    """Inspect a Python executable without importing repo code inside it."""

    code = r"""
import importlib.util, json, os, sys
mods = {}
for name in %r:
    mods[name] = importlib.util.find_spec(name) is not None
payload = {
    "executable": sys.executable,
    "version": sys.version.split()[0],
    "prefix": sys.prefix,
    "modules": mods,
    "cuda": {"available": False, "count": 0, "error": ""},
}
try:
    import torch
    payload["torch_version"] = getattr(torch, "__version__", "")
    payload["cuda"] = {
        "available": bool(torch.cuda.is_available()),
        "count": int(torch.cuda.device_count()),
        "error": "",
    }
except Exception as exc:
    payload["cuda"]["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(payload, ensure_ascii=False))
""" % (REQUIRED_RESEARCH_MODULES,)
    try:
        proc = subprocess.run(
            [python_bin, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return {"executable": python_bin, "ok": False, "error": str(exc), "modules": {}, "cuda": {}}
    if proc.returncode != 0:
        return {
            "executable": python_bin,
            "ok": False,
            "error": (proc.stderr or proc.stdout).strip(),
            "modules": {},
            "cuda": {},
        }
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return {"executable": python_bin, "ok": False, "error": str(exc), "modules": {}, "cuda": {}}
    payload["ok"] = True
    payload["research_ready"] = all(payload.get("modules", {}).get(name) for name in ("torch", "transformers", "datasets"))
    return payload


def runtime_status() -> dict[str, Any]:
    """Choose the best Python runtime for autonomous experiments."""

    candidates: list[dict[str, Any]] = []
    selected = None
    for python_bin in candidate_pythons():
        item = inspect_python(python_bin)
        candidates.append(item)
        if item.get("ok") and item.get("research_ready"):
            selected = item
            break
    if selected is None:
        for item in candidates:
            if item.get("ok"):
                selected = item
                break
    if selected is None:
        selected = {"executable": sys.executable, "ok": False, "modules": {}, "cuda": {}}
    return {
        "selected": selected,
        "candidates": candidates[:8],
        "required_modules": list(REQUIRED_RESEARCH_MODULES),
    }


def env_for_subprocess(base: dict[str, str] | None = None, status: dict[str, Any] | None = None) -> dict[str, str]:
    """Build an environment that points child tools at the selected runtime."""

    env = dict(base or os.environ)
    selected = (status or runtime_status()).get("selected", {})
    python_bin = str(selected.get("executable") or "")
    if python_bin:
        env["PAPERFACTORY_PYTHON"] = python_bin
        env["PYTHON_BIN"] = python_bin
        bin_dir = str(Path(python_bin).parent)
        path = env.get("PATH", "")
        if bin_dir and not path.startswith(bin_dir + os.pathsep):
            env["PATH"] = bin_dir + os.pathsep + path
        prefix = str(selected.get("prefix") or "")
        if prefix:
            env["CONDA_PREFIX"] = prefix
            env_name = Path(prefix).name
            env["CONDA_DEFAULT_ENV"] = env_name
    return env


def prompt_context(status: dict[str, Any] | None = None) -> str:
    snapshot = status or runtime_status()
    selected = snapshot.get("selected", {})
    modules = selected.get("modules", {}) if isinstance(selected.get("modules"), dict) else {}
    missing = [name for name in snapshot.get("required_modules", []) if not modules.get(name)]
    cuda = selected.get("cuda", {}) if isinstance(selected.get("cuda"), dict) else {}
    lines = ["Runtime environment snapshot:"]
    lines.append(f"- Selected Python: {selected.get('executable') or 'unknown'}")
    lines.append(f"- Python version: {selected.get('version') or 'unknown'}")
    if selected.get("research_ready"):
        lines.append("- Research packages: torch/transformers/datasets are available.")
    else:
        lines.append(f"- Missing research packages in selected Python: {missing if missing else 'unknown'}")
    lines.append(
        f"- Torch CUDA: available={cuda.get('available', False)}, device_count={cuda.get('count', 0)}"
    )
    lines.append("- Guidance: use `$PAPERFACTORY_PYTHON` or the selected Python path for experiments instead of bare `python` when package availability matters.")
    lines.append("- If no suitable environment exists for a required baseline, create an isolated `.research/envs/<purpose>` environment and record the exact creation command and package versions.")
    return "\n".join(lines)
