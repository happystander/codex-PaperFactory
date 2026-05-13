"""Human intervention patches for PaperFactory."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


PATCH_DIR = "interventions"
PATCH_FILE = "interventions/patches.jsonl"
PATCH_KINDS = {"scope", "workflow", "memory", "stop_condition", "general"}


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def patch_path(root: Path) -> Path:
    return root / PATCH_FILE


def classify_patch(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ("scope", "research question", "研究范围", "研究问题")):
        return "scope"
    if any(token in lower for token in ("workflow", "phase", "阶段", "流程", "跳转")):
        return "workflow"
    if any(token in lower for token in ("memory", "记忆", "上下文")):
        return "memory"
    if any(token in lower for token in ("stop", "pause", "停止", "暂停", "成功条件", "success condition")):
        return "stop_condition"
    return "general"


def stable_id(text: str, created_at: str) -> str:
    return hashlib.sha1(f"{created_at}\n{text}".encode("utf-8")).hexdigest()[:14]


def append_patch(root: Path, message: str, *, kind: str | None = None) -> dict[str, Any]:
    text = message.strip()
    if not text:
        raise ValueError("intervention patch must not be empty")
    created_at = iso_now()
    patch_kind = kind if kind in PATCH_KINDS else classify_patch(text)
    patch = {
        "id": f"patch_{stable_id(text, created_at)}",
        "created_at": created_at,
        "status": "pending",
        "kind": patch_kind,
        "message": text,
        "applies_to": {
            "scope": patch_kind == "scope",
            "workflow": patch_kind == "workflow",
            "memory": patch_kind == "memory",
            "stop_conditions": patch_kind == "stop_condition",
        },
    }
    path = patch_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(patch, ensure_ascii=False, sort_keys=True) + "\n")
    return patch


def read_patches(root: Path, limit: int = 50) -> list[dict[str, Any]]:
    path = patch_path(root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows[-limit:]


def pending_patch_summary(root: Path, limit: int = 20) -> dict[str, Any]:
    patches = read_patches(root, limit=200)
    pending = [item for item in patches if item.get("status") == "pending"]
    return {
        "patches_file": PATCH_FILE,
        "pending_count": len(pending),
        "recent_pending": pending[-limit:],
    }

