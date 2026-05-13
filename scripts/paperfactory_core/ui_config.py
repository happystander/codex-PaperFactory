"""User-facing UI and agent language configuration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


UI_CONFIG = "ui_config.json"
SUPPORTED_LANGUAGES = {"zh", "en"}


def iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def normalize_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"en", "english", "en-us", "en-gb"}:
        return "en"
    return "zh"


def ui_config_path(root: Path) -> Path:
    return root / UI_CONFIG


def default_ui_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": iso_now(),
        "language": "zh",
    }


def read_ui_config(root: Path) -> dict[str, Any]:
    config = default_ui_config()
    path = ui_config_path(root)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            config.update(data)
    config["language"] = normalize_language(config.get("language"))
    config["language_label"] = "English" if config["language"] == "en" else "中文"
    config["language_name"] = "English" if config["language"] == "en" else "Simplified Chinese"
    return config


def write_ui_config(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    current = read_ui_config(root)
    if "language" in config:
        current["language"] = normalize_language(config.get("language"))
    current["schema_version"] = 1
    current["updated_at"] = iso_now()
    path = ui_config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return read_ui_config(root)


def language_instruction(root: Path) -> str:
    config = read_ui_config(root)
    if config["language"] == "en":
        return (
            "User-facing language: English.\n"
            "- Write all progress feed messages, phase-page prose, stage replies, review summaries, "
            "and human-facing report summaries in English.\n"
            "- Keep JSON keys, artifact paths, commands, identifiers, citations, and quoted source titles unchanged."
        )
    return (
        "User-facing language: Simplified Chinese.\n"
        "- 所有 progress feed 消息、阶段展示页正文、阶段回复、审稿摘要和面向用户的报告摘要都必须使用简体中文。\n"
        "- JSON key、产物路径、命令、标识符、引用和原文标题保持原样，不要翻译。"
    )
