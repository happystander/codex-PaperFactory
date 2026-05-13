"""Web-facing memory profile configuration for PaperFactory."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import researchctl


MEMORY_CONFIG = "memory_config.json"
MEMORY_PROFILES: dict[str, dict[str, Any]] = {
    "focused": {
        "label": "轻量记忆",
        "description": "适合快速迭代：读取阶段交接、研究摘要和人工介入，减少旧信息干扰。",
        "config": {"summary": True, "logs": False, "human_interventions": True, "artifact_index": False},
    },
    "balanced": {
        "label": "标准记忆",
        "description": "推荐：读取阶段交接、阶段摘要、人工介入、产物索引和 claim/evidence 记忆。",
        "config": {"summary": True, "logs": False, "human_interventions": True, "artifact_index": True},
    },
    "deep": {
        "label": "深度记忆",
        "description": "适合排错或长链路恢复：额外读取日志、决策记忆和风险记忆。",
        "config": {"summary": True, "logs": True, "human_interventions": True, "artifact_index": True},
    },
    "clean": {
        "label": "干净启动",
        "description": "只保留任务、阶段交接和人工介入，适合想降低旧上下文影响时使用。",
        "config": {"summary": False, "logs": False, "human_interventions": True, "artifact_index": False},
    },
}


def memory_config_path(root: Path) -> Path:
    return root / MEMORY_CONFIG


def memory_bundle_status(root: Path) -> dict[str, Any]:
    names = (
        "handoff.md",
        "phase_summaries.jsonl",
        "artifact_index.json",
        "decision_memory.json",
        "risk_memory.json",
        "claim_memory.json",
    )
    files: dict[str, dict[str, Any]] = {}
    mtimes: list[float] = []
    for name in names:
        path = root / "memory" / name
        row: dict[str, Any] = {"exists": False, "path": f"memory/{name}"}
        try:
            stat = path.stat()
        except OSError:
            stat = None
        if stat and stat.st_size > 0:
            row.update(
                {
                    "exists": True,
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                }
            )
            mtimes.append(stat.st_mtime)
        files[name] = row
    return {
        "dir": "memory/",
        "ready": bool(files["handoff.md"]["exists"]),
        "updated_at": datetime.fromtimestamp(max(mtimes)).astimezone().isoformat() if mtimes else "",
        "files": files,
    }


def default_memory_config() -> dict[str, Any]:
    config = dict(MEMORY_PROFILES["balanced"]["config"])
    config["profile"] = "balanced"
    return config


def memory_profile_for(config: dict[str, Any]) -> str:
    for name, profile in MEMORY_PROFILES.items():
        if all(bool(config.get(key)) == bool(value) for key, value in profile["config"].items()):
            return name
    return "custom"


def read_memory_config(root: Path) -> dict[str, Any]:
    config = default_memory_config()
    path = memory_config_path(root)
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
        if isinstance(raw, dict):
            for key in ("summary", "logs", "human_interventions", "artifact_index"):
                if key in raw:
                    config[key] = bool(raw[key])
            if str(raw.get("profile") or "") in MEMORY_PROFILES:
                config["profile"] = str(raw["profile"])
    profile_name = memory_profile_for(config)
    if profile_name == "custom":
        config["profile"] = "custom"
        config["label"] = "自定义记忆"
        config["description"] = "你手动选择了记忆来源。"
    else:
        config["profile"] = profile_name
        config["label"] = str(MEMORY_PROFILES[profile_name]["label"])
        config["description"] = str(MEMORY_PROFILES[profile_name]["description"])
    config["profiles"] = {
        key: {"label": value["label"], "description": value["description"]}
        for key, value in MEMORY_PROFILES.items()
    }
    bundle = memory_bundle_status(root)
    if not bundle["ready"] and researchctl.state_path(root).exists():
        try:
            researchctl.refresh_memory(root, researchctl.load_state(root))
            bundle = memory_bundle_status(root)
        except Exception:
            pass
    config["bundle"] = bundle
    return config


def write_memory_config(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    current = read_memory_config(root)
    profile = str(config.get("profile") or "")
    if profile in MEMORY_PROFILES:
        for key, value in MEMORY_PROFILES[profile]["config"].items():
            current[key] = bool(value)
        current["profile"] = profile
    for key in ("summary", "logs", "human_interventions", "artifact_index"):
        if key in config:
            current[key] = bool(config[key])
    persist = {
        key: current[key]
        for key in ("profile", "summary", "logs", "human_interventions", "artifact_index")
        if key in current
    }
    memory_config_path(root).write_text(json.dumps(persist, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        researchctl.refresh_memory(root, researchctl.load_state(root))
    except Exception as exc:
        researchctl.append_log(root, f"Memory bundle refresh failed after config update: {exc}")
    researchctl.append_log(root, "Web UI memory config updated")
    return read_memory_config(root)

