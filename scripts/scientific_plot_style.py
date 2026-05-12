#!/usr/bin/env python3
"""Reusable matplotlib style helpers for Codex PaperFactory figures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterable


SCI_COLORS = {
    "blue": "#2563EB",
    "green": "#16A34A",
    "red": "#DC2626",
    "gray": "#525252",
    "purple": "#7C3AED",
    "orange": "#EA580C",
}

SCI_PALETTE = [
    SCI_COLORS["blue"],
    SCI_COLORS["green"],
    SCI_COLORS["red"],
    SCI_COLORS["purple"],
    SCI_COLORS["gray"],
    SCI_COLORS["orange"],
]


def cm_to_inch(value_cm: float) -> float:
    return value_cm / 2.54


def ensure_matplotlib_configdir() -> None:
    if os.environ.get("MPLCONFIGDIR"):
        return
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", tempfile.gettempdir()))
    cache_dir = cache_root / "codex-paper-factory-matplotlib"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(cache_dir)
    except OSError:
        fallback = Path(tempfile.gettempdir()) / "codex-paper-factory-matplotlib"
        fallback.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(fallback)


def figure_size(kind: str = "single") -> tuple[float, float]:
    if kind == "double":
        return cm_to_inch(17.8), cm_to_inch(10.5)
    if kind == "square":
        return cm_to_inch(8.5), cm_to_inch(8.5)
    return cm_to_inch(8.5), cm_to_inch(6.375)


def apply_paper_style(font_size: float = 7.5, full_box: bool = False) -> None:
    ensure_matplotlib_configdir()
    import matplotlib as mpl

    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "font.size": font_size,
            "axes.labelsize": font_size,
            "axes.titlesize": font_size + 0.5,
            "xtick.labelsize": font_size - 0.5,
            "ytick.labelsize": font_size - 0.5,
            "legend.fontsize": font_size - 0.5,
            "axes.linewidth": 0.8,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "legend.frameon": False,
            "legend.handlelength": 1.2,
            "legend.labelspacing": 0.35,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.02,
        }
    )
    if full_box:
        mpl.rcParams.update({"xtick.top": True, "ytick.right": True})


def clean_axes(ax, full_box: bool = False, grid: bool = False) -> None:
    ax.spines["top"].set_visible(full_box)
    ax.spines["right"].set_visible(full_box)
    if grid:
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.6)
        ax.set_axisbelow(True)


def save_figure(fig, output_base: str | Path, formats: Iterable[str] = ("svg", "pdf"), dpi: int = 600) -> list[Path]:
    output = Path(output_base)
    output.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fmt in formats:
        path = output.with_suffix(f".{fmt}")
        if fmt.lower() in {"png", "tiff", "tif"}:
            fig.savefig(path, dpi=dpi)
        else:
            fig.savefig(path)
        written.append(path)
    return written
