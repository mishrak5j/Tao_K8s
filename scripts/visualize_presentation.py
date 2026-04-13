#!/usr/bin/env python3
"""
Generate four presentation-quality visualizations from runs/*/metrics.csv.

Charts produced:
  1. Grouped bar chart   – mean pod duration per model x strategy
  2. Box-and-whisker plot – per-pod duration distribution (jitter / predictability)
  3. Heatmap             – % change in duration vs the Default baseline
  4. Pareto scatter       – throughput vs aggregate resource-time cost

Uses the latest run folder (by timestamp prefix) for each (model, strategy) pair,
identical to the selection logic in visualize_runs.py.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR_DEFAULT = REPO_ROOT / "runs"

FOLDER_RE = re.compile(r"^(\d{8}T\d{6}Z)_(.+)_(default|binpack|spread)$")

STRATEGIES = ("default", "binpack", "spread")
STRATEGY_LABEL = {"default": "Default", "binpack": "Binpack", "spread": "Spread"}
STRATEGY_COLOR = {"default": "#4C72B0", "binpack": "#55A868", "spread": "#C44E52"}
MODEL_DISPLAY = {"bert": "BERT", "dlrm": "DLRM", "resnet": "ResNet", "yolo": "YOLO"}
MODEL_MARKER = {"bert": "o", "dlrm": "s", "resnet": "D", "yolo": "^"}

DPI = 200

# ---------------------------------------------------------------------------
# Data loading (mirrors visualize_runs.py)
# ---------------------------------------------------------------------------


def _parse_folder(name: str) -> tuple[str, str, str] | None:
    m = FOLDER_RE.match(name)
    if not m:
        return None
    return m.groups()  # type: ignore[return-value]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _row_duration(row: dict[str, str]) -> float | None:
    s = (row.get("total_duration_seconds") or "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def collect_latest_runs(runs_dir: Path) -> dict[tuple[str, str], Path]:
    """Return {(model, strategy): metrics.csv} keeping only the latest timestamp."""
    best: dict[tuple[str, str], tuple[str, Path]] = {}
    for metrics in sorted(runs_dir.glob("*/metrics.csv")):
        parsed = _parse_folder(metrics.parent.name)
        if not parsed:
            continue
        ts, model, strategy = parsed
        key = (model, strategy)
        prev = best.get(key)
        if prev is None or ts > prev[0]:
            best[key] = (ts, metrics)
    return {k: v[1] for k, v in best.items()}


def load_durations(csv_path: Path) -> list[float]:
    return [d for row in _load_csv(csv_path) if (d := _row_duration(row)) is not None]


def mean_std(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return float("nan"), float("nan")
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return m, math.sqrt(var)


# ---------------------------------------------------------------------------
# Chart 1 – Grouped Bar Chart (Mean Latency)
# ---------------------------------------------------------------------------


def plot_grouped_bar(
    out_path: Path,
    models: list[str],
    data: dict[tuple[str, str], list[float]],
) -> None:
    n_models = len(models)
    n_strategies = len(STRATEGIES)
    bar_width = 0.25
    x = np.arange(n_models)

    fig, ax = plt.subplots(figsize=(10, 6))

    for idx, strat in enumerate(STRATEGIES):
        means, stds = [], []
        for model in models:
            durs = data.get((model, strat), [])
            mu, sd = mean_std(durs)
            means.append(mu)
            stds.append(sd if math.isfinite(sd) else 0.0)
        offset = (idx - (n_strategies - 1) / 2) * bar_width
        bars = ax.bar(
            x + offset,
            means,
            bar_width,
            yerr=stds,
            capsize=4,
            label=STRATEGY_LABEL[strat],
            color=STRATEGY_COLOR[strat],
            edgecolor="white",
            linewidth=0.8,
            zorder=3,
        )
        for bar, mu in zip(bars, means):
            if math.isfinite(mu):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 2,
                    f"{mu:.1f}s",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    fontweight="bold",
                    color="#333333",
                )

    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_DISPLAY.get(m, m.upper()) for m in models], fontsize=11)
    ax.set_ylabel("Mean Pod Duration (seconds)", fontsize=11)
    ax.set_title(
        "Performance Baseline: Mean Training Duration by Scheduler Strategy",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )
    ax.legend(framealpha=0.9, fontsize=10)
    ax.grid(axis="y", alpha=0.25, zorder=0)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 2 – Box & Whisker Plot (Predictability / Jitter)
# ---------------------------------------------------------------------------


def plot_boxplot(
    out_path: Path,
    models: list[str],
    data: dict[tuple[str, str], list[float]],
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes_flat = axes.ravel()

    for ax, model in zip(axes_flat, models):
        box_data = []
        positions = []
        colors = []
        for idx, strat in enumerate(STRATEGIES):
            durs = data.get((model, strat), [])
            box_data.append(durs if durs else [0])
            positions.append(idx)
            colors.append(STRATEGY_COLOR[strat])

        bp = ax.boxplot(
            box_data,
            positions=positions,
            widths=0.5,
            patch_artist=True,
            showmeans=True,
            meanprops=dict(marker="D", markerfacecolor="white", markeredgecolor="black", markersize=5),
            medianprops=dict(color="black", linewidth=1.5),
            whiskerprops=dict(linewidth=1.2),
            capprops=dict(linewidth=1.2),
            flierprops=dict(marker="o", markersize=4, alpha=0.6),
        )
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        rng = np.random.default_rng(42)
        for idx, strat in enumerate(STRATEGIES):
            durs = data.get((model, strat), [])
            if durs:
                jitter = rng.uniform(-0.12, 0.12, size=len(durs))
                ax.scatter(
                    [idx + j for j in jitter],
                    durs,
                    color=STRATEGY_COLOR[strat],
                    edgecolor="white",
                    linewidth=0.5,
                    s=28,
                    alpha=0.8,
                    zorder=5,
                )

        ax.set_xticks(positions)
        ax.set_xticklabels([STRATEGY_LABEL[s] for s in STRATEGIES], fontsize=10)
        ax.set_ylabel("Pod Duration (seconds)", fontsize=9)
        ax.set_title(MODEL_DISPLAY.get(model, model.upper()), fontsize=12, fontweight="bold")
        ax.grid(axis="y", alpha=0.25)

    for j in range(len(models), len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.suptitle(
        "Predictability Analysis: Pod Duration Distribution by Strategy",
        fontsize=14,
        fontweight="bold",
        y=1.01,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 3 – Heatmap (% Change vs Default Baseline)
# ---------------------------------------------------------------------------


def plot_heatmap(
    out_path: Path,
    models: list[str],
    data: dict[tuple[str, str], list[float]],
) -> None:
    compare_strats = ("binpack", "spread")
    mat: list[list[float]] = []
    for model in models:
        base_mu, _ = mean_std(data.get((model, "default"), []))
        row = []
        for strat in compare_strats:
            mu, _ = mean_std(data.get((model, strat), []))
            if math.isfinite(base_mu) and base_mu > 0 and math.isfinite(mu):
                row.append((mu - base_mu) / base_mu * 100.0)
            else:
                row.append(float("nan"))
        mat.append(row)

    arr = np.array(mat)

    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(arr, cmap="RdYlGn_r", aspect="auto", vmin=-50, vmax=50)

    ax.set_xticks(range(len(compare_strats)))
    ax.set_xticklabels(
        [f"{STRATEGY_LABEL[s]} vs Default" for s in compare_strats],
        fontsize=11,
    )
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([MODEL_DISPLAY.get(m, m.upper()) for m in models], fontsize=11)

    for i in range(len(models)):
        for j in range(len(compare_strats)):
            v = arr[i, j]
            if math.isfinite(v):
                label = f"{v:+.1f}%"
                qualifier = "slower" if v > 0 else "faster"
                text = f"{label}\n({qualifier})"
            else:
                text = "N/A"
            ax.text(
                j,
                i,
                text,
                ha="center",
                va="center",
                fontsize=11,
                fontweight="bold",
                color="black",
            )

    ax.set_title(
        'The "Scheduling Penalty": Duration Change vs Default Baseline',
        fontsize=13,
        fontweight="bold",
        pad=14,
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("% Change in Mean Duration", fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Chart 4 – Pareto Scatter Plot (Throughput vs Cost)
# ---------------------------------------------------------------------------


def plot_pareto(
    out_path: Path,
    models: list[str],
    data: dict[tuple[str, str], list[float]],
) -> None:
    fig, ax = plt.subplots(figsize=(10, 7))

    points: list[tuple[float, float, str, str]] = []

    for model in models:
        for strat in STRATEGIES:
            durs = data.get((model, strat), [])
            if not durs:
                continue
            n_pods = len(durs)
            max_dur = max(durs)
            mu, _ = mean_std(durs)
            if max_dur <= 0 or not math.isfinite(mu):
                continue

            throughput = n_pods / (max_dur / 60.0)  # pods per minute
            cost = mu * n_pods  # total pod-seconds

            points.append((throughput, cost, model, strat))
            ax.scatter(
                throughput,
                cost,
                c=STRATEGY_COLOR[strat],
                marker=MODEL_MARKER[model],
                s=140,
                edgecolor="white",
                linewidth=0.8,
                zorder=5,
            )
            ax.annotate(
                f"{MODEL_DISPLAY.get(model, model)}\n({STRATEGY_LABEL[strat]})",
                (throughput, cost),
                textcoords="offset points",
                xytext=(10, 6),
                fontsize=7.5,
                ha="left",
                va="bottom",
                color="#333333",
            )

    # Draw Pareto frontier (non-dominated: higher throughput AND lower cost)
    if points:
        sorted_pts = sorted(points, key=lambda p: p[0])
        frontier_x, frontier_y = [], []
        best_cost = float("inf")
        for tp, cost, _, _ in reversed(sorted_pts):
            if cost <= best_cost:
                frontier_x.append(tp)
                frontier_y.append(cost)
                best_cost = cost
        frontier_x.reverse()
        frontier_y.reverse()
        if len(frontier_x) >= 2:
            ax.plot(
                frontier_x,
                frontier_y,
                linestyle="--",
                color="#888888",
                linewidth=1.2,
                alpha=0.7,
                label="Pareto Frontier",
                zorder=2,
            )

    # Legend entries for strategies and models
    for strat in STRATEGIES:
        ax.scatter([], [], c=STRATEGY_COLOR[strat], s=80, label=f"Strategy: {STRATEGY_LABEL[strat]}")
    for model in models:
        ax.scatter([], [], c="gray", marker=MODEL_MARKER[model], s=80, label=f"Model: {MODEL_DISPLAY.get(model, model)}")

    ax.set_xlabel("Throughput (pods completed / minute)", fontsize=11)
    ax.set_ylabel("Resource-Time Cost (total pod-seconds)", fontsize=11)
    ax.set_title(
        "Pareto Frontier: Throughput vs Infrastructure Cost",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )
    ax.legend(
        loc="upper right",
        fontsize=8,
        framealpha=0.9,
        ncol=2,
    )
    ax.grid(alpha=0.25, zorder=0)
    ax.set_axisbelow(True)

    ax.annotate(
        "Cost proxy = mean_duration x n_pods (total pod-seconds).\n"
        "Ideal position: high throughput, low cost (bottom-right).",
        xy=(0.02, 0.02),
        xycoords="axes fraction",
        fontsize=7.5,
        color="#666666",
        va="bottom",
        ha="left",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#cccccc", alpha=0.8),
    )

    fig.tight_layout()
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate four presentation-quality visualizations from experiment runs."
    )
    ap.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR_DEFAULT,
        help="Directory containing run subfolders (default: <repo>/runs)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for PNGs (default: <runs-dir>/plots)",
    )
    args = ap.parse_args()

    runs_dir: Path = args.runs_dir
    out_dir: Path = args.out_dir or (runs_dir / "plots")
    out_dir.mkdir(parents=True, exist_ok=True)

    latest = collect_latest_runs(runs_dir)
    if not latest:
        raise SystemExit(f"No metrics.csv found under {runs_dir}")

    models = sorted({m for m, _ in latest})
    data: dict[tuple[str, str], list[float]] = {}
    for key, csv_path in latest.items():
        data[key] = load_durations(csv_path)

    files = [
        ("grouped_bar_mean_latency.png", plot_grouped_bar),
        ("boxplot_duration_jitter.png", plot_boxplot),
        ("heatmap_pct_change.png", plot_heatmap),
        ("pareto_scatter.png", plot_pareto),
    ]
    for fname, fn in files:
        path = out_dir / fname
        fn(path, models, data)
        print(f"  wrote {path}")

    print(f"\nAll 4 presentation charts saved to {out_dir}")


if __name__ == "__main__":
    main()
