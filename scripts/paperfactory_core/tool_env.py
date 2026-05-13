"""Isolated lightweight optional-tool environments for PaperFactory."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import venv
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path.home() / ".local" / "share" / "paperfactory" / "tools"
BIN_DIR = Path.home() / ".local" / "bin"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    packages: tuple[str, ...]
    commands: tuple[str, ...]
    modules: tuple[str, ...]
    description: str


TOOL_SPECS: dict[str, ToolSpec] = {
    "literature": ToolSpec(
        name="literature",
        packages=("scholaraio", "arxiv", "habanero", "semanticscholar", "markitdown", "pypdf", "pdfminer.six"),
        commands=("scholaraio",),
        modules=("scholaraio", "arxiv", "habanero", "semanticscholar", "markitdown", "pypdf", "pdfminer"),
        description="literature APIs, ScholarAIO, Office/PDF conversion helpers",
    ),
    "pandoc": ToolSpec(
        name="pandoc",
        packages=("pypandoc_binary",),
        commands=("pandoc",),
        modules=("pypandoc",),
        description="Pandoc document conversion through pypandoc binary",
    ),
}


def tools_root() -> Path:
    return Path(os.environ.get("PAPERFACTORY_TOOLS_HOME", str(DEFAULT_ROOT))).expanduser()


def env_dir(name: str) -> Path:
    return tools_root() / name


def python_bin(name: str) -> Path:
    return env_dir(name) / "bin" / "python"


def bin_path(name: str, command: str) -> Path:
    return env_dir(name) / "bin" / command


def available_specs(names: list[str] | None = None) -> list[ToolSpec]:
    if not names or names == ["all"]:
        return list(TOOL_SPECS.values())
    specs: list[ToolSpec] = []
    for name in names:
        if name not in TOOL_SPECS:
            raise ValueError(f"Unknown tool env: {name}. Available: {', '.join(sorted(TOOL_SPECS))}")
        specs.append(TOOL_SPECS[name])
    return specs


def ensure_env(name: str, *, recreate: bool = False) -> Path:
    path = env_dir(name)
    if recreate and path.exists():
        shutil.rmtree(path)
    if not python_bin(name).exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        venv.EnvBuilder(with_pip=True, symlinks=True).create(path)
    return path


def install_spec(spec: ToolSpec, *, recreate: bool = False) -> None:
    ensure_env(spec.name, recreate=recreate)
    cmd = [str(python_bin(spec.name)), "-m", "pip", "install", "-U", "pip", *spec.packages]
    subprocess.check_call(cmd)
    link_commands(spec)
    write_metadata(spec)


def wrapper_text(spec: ToolSpec, command: str) -> str:
    if spec.name == "pandoc" and command == "pandoc":
        return textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            exec {python_bin(spec.name)} -c 'import os, sys, pypandoc; path = os.path.join(os.path.dirname(os.path.realpath(pypandoc.__file__)), "files", "pandoc"); os.execv(path, [path, *sys.argv[1:]])' "$@"
            """
        )
    target = bin_path(spec.name, command)
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        exec {target} "$@"
        """
    )


def link_commands(spec: ToolSpec) -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for command in spec.commands:
        wrapper = BIN_DIR / command
        wrapper.write_text(wrapper_text(spec, command), encoding="utf-8")
        wrapper.chmod(0o755)


def write_metadata(spec: ToolSpec) -> None:
    payload = {
        "name": spec.name,
        "packages": list(spec.packages),
        "commands": list(spec.commands),
        "modules": list(spec.modules),
        "description": spec.description,
        "python": str(python_bin(spec.name)),
    }
    path = env_dir(spec.name) / "paperfactory-tool.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def check_spec(spec: ToolSpec) -> dict[str, Any]:
    py = python_bin(spec.name)
    command_status: dict[str, bool] = {}
    module_status: dict[str, bool] = {}
    if py.exists():
        for module in spec.modules:
            proc = subprocess.run(
                [str(py), "-c", f"import {module}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            module_status[module] = proc.returncode == 0
    for command in spec.commands:
        command_status[command] = shutil.which(command) is not None
    ok = bool(py.exists()) and all(module_status.get(item, False) for item in spec.modules)
    if spec.commands:
        ok = ok and all(command_status.get(item, False) for item in spec.commands)
    return {
        "name": spec.name,
        "ok": ok,
        "path": str(env_dir(spec.name)),
        "python": str(py),
        "description": spec.description,
        "modules": module_status,
        "commands": command_status,
        "installed": py.exists(),
    }


def list_status(names: list[str] | None = None) -> list[dict[str, Any]]:
    return [check_spec(spec) for spec in available_specs(names)]


def command_path(command: str) -> str | None:
    found = shutil.which(command)
    if found:
        return found
    for spec in TOOL_SPECS.values():
        if command in spec.commands:
            wrapper = BIN_DIR / command
            if wrapper.exists():
                return str(wrapper)
            target = bin_path(spec.name, command)
            if target.exists():
                return str(target)
    return None


def module_available(module: str) -> str | None:
    try:
        __import__(module)
        return sys.executable
    except Exception:
        pass
    for spec in TOOL_SPECS.values():
        if module not in spec.modules:
            continue
        py = python_bin(spec.name)
        if not py.exists():
            continue
        proc = subprocess.run([str(py), "-c", f"import {module}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode == 0:
            return str(py)
    return None
