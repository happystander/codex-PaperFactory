#!/usr/bin/env python3
"""Create a simple paper-style metric plot from CSV or JSON records."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scientific_plot_style import (
    SCI_PALETTE,
    apply_paper_style,
    clean_axes,
    ensure_matplotlib_configdir,
    figure_size,
    save_figure,
)


def load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [dict(row) for row in data]
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [dict(row) for row in data["records"]]
    if isinstance(data, dict) and isinstance(data.get("metrics"), dict):
        rows = []
        for name, metrics in data["metrics"].items():
            row = {"method": name}
            if isinstance(metrics, dict):
                row.update(metrics)
            rows.append(row)
        return rows
    raise ValueError("Input must be CSV, a JSON list, {'records': [...]}, or {'metrics': {...}}")


def to_float(value: Any) -> float:
    if value is None or value == "":
        return float("nan")
    return float(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="CSV or JSON metrics file")
    parser.add_argument("--x", default="method", help="Column used for x labels")
    parser.add_argument("--y", required=True, help="Metric column to plot")
    parser.add_argument("--group", help="Optional group column for line plots")
    parser.add_argument("--kind", choices=["bar", "line"], default="bar")
    parser.add_argument("--title", default="")
    parser.add_argument("--ylabel", default="")
    parser.add_argument("--output", required=True, help="Output path without extension, or with extension")
    parser.add_argument("--size", choices=["single", "double", "square"], default="single")
    parser.add_argument("--formats", default="svg,pdf", help="Comma-separated output formats")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_records(Path(args.input))
    if not records:
        raise SystemExit("No records found.")

    ensure_matplotlib_configdir()
    import matplotlib.pyplot as plt

    apply_paper_style()
    fig, ax = plt.subplots(figsize=figure_size(args.size))

    if args.kind == "line":
        if args.group:
            groups: dict[str, list[dict[str, Any]]] = {}
            for row in records:
                groups.setdefault(str(row.get(args.group, "")), []).append(row)
            for idx, (group, rows) in enumerate(groups.items()):
                ax.plot(
                    [str(row.get(args.x, "")) for row in rows],
                    [to_float(row.get(args.y)) for row in rows],
                    marker="o",
                    linewidth=1.5,
                    markersize=3.2,
                    color=SCI_PALETTE[idx % len(SCI_PALETTE)],
                    label=group,
                )
            ax.legend()
        else:
            ax.plot(
                [str(row.get(args.x, "")) for row in records],
                [to_float(row.get(args.y)) for row in records],
                marker="o",
                linewidth=1.5,
                markersize=3.2,
                color=SCI_PALETTE[0],
            )
    else:
        labels = [str(row.get(args.x, "")) for row in records]
        values = [to_float(row.get(args.y)) for row in records]
        ax.barh(labels, values, color=SCI_PALETTE[0], edgecolor="none")
        ax.invert_yaxis()

    ax.set_title(args.title)
    ax.set_xlabel(args.ylabel or args.y)
    clean_axes(ax, grid=args.kind == "bar")
    if args.kind == "line":
        ax.tick_params(axis="x", rotation=30)
        ax.set_ylabel(args.ylabel or args.y)
        ax.set_xlabel(args.x)
    else:
        ax.set_ylabel("")

    output = Path(args.output)
    output_base = output.with_suffix("") if output.suffix else output
    formats = [fmt.strip().lstrip(".") for fmt in args.formats.split(",") if fmt.strip()]
    written = save_figure(fig, output_base, formats=formats)
    print(json.dumps({"outputs": [str(path) for path in written]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
