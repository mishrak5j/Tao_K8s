#!/usr/bin/env python3
"""
Aggregate runs/*/metrics.csv and plot scheduler strategy vs workload.

Uses the latest run folder (by timestamp prefix) for each (model, strategy) pair.
DLRM final_loss is omitted from metric plots (numerically unstable); duration is still shown.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR_DEFAULT = REPO_ROOT / "runs"

FOLDER_RE = re.compile(r"^(\d{8}T\d{6}Z)_(.+)_(default|binpack|spread)$")

STRATEGIES = ("default", "binpack", "spread")
STRATEGY_LABEL = {"default": "Default", "binpack": "Binpack", "spread": "Spread"}
STRATEGY_COLOR = {"default": "#4C72B0", "binpack": "#55A868", "spread": "#C44E52"}


def parse_folder(name: str) -> tuple[str, str, str] | None:
    m = FOLDER_RE.match(name)
    if not m:
        return None
    ts, model, strategy = m.groups()
    return ts, model, strategy


def load_metrics_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def row_duration(row: dict[str, str]) -> float | None:
    s = (row.get("total_duration_seconds") or "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def row_metric_value(row: dict[str, str]) -> float | None:
    s = (row.get("value") or "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v


def collect_latest_runs(
    runs_dir: Path,
) -> dict[tuple[str, str], tuple[str, Path]]:
    """Map (model, strategy) -> (timestamp, path to metrics.csv)."""
    best: dict[tuple[str, str], tuple[str, Path]] = {}
    for metrics in sorted(runs_dir.glob("*/metrics.csv")):
        parsed = parse_folder(metrics.parent.name)
        if not parsed:
            continue
        ts, model, strategy = parsed
        key = (model, strategy)
        prev = best.get(key)
        if prev is None or ts > prev[0]:
            best[key] = (ts, metrics)
    return best


def summarize_run(metrics_path: Path) -> tuple[list[float], list[float], str | None, str | None]:
    rows = load_metrics_csv(metrics_path)
    durations: list[float] = []
    values: list[float] = []
    metric_name: str | None = None
    task_name: str | None = None
    for row in rows:
        d = row_duration(row)
        if d is not None:
            durations.append(d)
        v = row_metric_value(row)
        if v is not None:
            values.append(v)
        m = (row.get("metric") or "").strip()
        if m and metric_name is None:
            metric_name = m
        t = (row.get("task_name") or "").strip()
        if t and task_name is None:
            task_name = t
    return durations, values, metric_name, task_name


def mean_std(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return float("nan"), float("nan")
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return m, math.sqrt(var)


def plot_duration_subplots(
    out_path: Path,
    models: list[str],
    by_ms: dict[tuple[str, str], tuple[list[float], list[float], str | None, str | None]],
) -> None:
    n = len(models)
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), sharey=False)
    axes_flat = axes.ravel()
    for ax, model in zip(axes_flat, models):
        means = []
        stds = []
        for s in STRATEGIES:
            durs, _, _, _ = by_ms.get((model, s), ([], [], None, None))
            mu, sd = mean_std(durs)
            means.append(mu)
            stds.append(sd if math.isfinite(sd) else 0.0)
        x = range(len(STRATEGIES))
        bars = ax.bar(
            x,
            means,
            yerr=stds,
            capsize=4,
            color=[STRATEGY_COLOR[s] for s in STRATEGIES],
            edgecolor="white",
            linewidth=0.8,
        )
        ax.set_xticks(list(x))
        ax.set_xticklabels([STRATEGY_LABEL[s] for s in STRATEGIES], rotation=15, ha="right")
        ax.set_ylabel("Mean pod duration (s)")
        ax.set_title(model.upper())
        ax.grid(axis="y", alpha=0.25)
        # annotate % vs default when computable
        base = means[0] if means and math.isfinite(means[0]) and means[0] > 0 else None
        if base is not None:
            for i, (b, mu) in enumerate(zip(bars, means)):
                if i == 0 or not math.isfinite(mu):
                    continue
                pct = (mu - base) / base * 100.0
                ax.annotate(
                    f"{pct:+.0f}%",
                    xy=(b.get_x() + b.get_width() / 2, mu + stds[i]),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="#333333",
                )
    for j in range(len(models), len(axes_flat)):
        axes_flat[j].set_visible(False)
    fig.suptitle("Scheduler comparison: wall-clock time per pod (mean ± std)", fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_metric_subplots(
    out_path: Path,
    models_metric: list[str],
    by_ms: dict[tuple[str, str], tuple[list[float], list[float], str | None, str | None]],
) -> None:
    n = len(models_metric)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4), squeeze=False)
    axes_flat = axes[0]
    for ax, model in zip(axes_flat, models_metric):
        metric_label: str | None = None
        means = []
        stds = []
        for s in STRATEGIES:
            _, vals, mname, _ = by_ms.get((model, s), ([], [], None, None))
            if mname and metric_label is None:
                metric_label = mname
            mu, sd = mean_std(vals)
            means.append(mu)
            stds.append(sd if math.isfinite(sd) else 0.0)
        x = range(len(STRATEGIES))
        ax.bar(
            x,
            means,
            yerr=stds,
            capsize=4,
            color=[STRATEGY_COLOR[s] for s in STRATEGIES],
            edgecolor="white",
            linewidth=0.8,
        )
        ax.set_xticks(list(x))
        ax.set_xticklabels([STRATEGY_LABEL[s] for s in STRATEGIES], rotation=15, ha="right")
        ylab = metric_label or "metric"
        ax.set_ylabel(ylab)
        ax.set_title(f"{model.upper()} ({ylab})")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Workload metric by scheduler (mean ± std across pods)", fontsize=13, y=1.05)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_heatmap_duration_pct(
    out_path: Path,
    models: list[str],
    by_ms: dict[tuple[str, str], tuple[list[float], list[float], str | None, str | None]],
) -> None:
    """Heatmap: rows=models, cols=binpack/spread; cell = % slower/faster vs default mean duration."""
    mat: list[list[float]] = []
    for model in models:
        row = []
        d0, _, _, _ = by_ms.get((model, "default"), ([], [], None, None))
        base_mu, _ = mean_std(d0)
        if not math.isfinite(base_mu) or base_mu <= 0:
            row.extend([math.nan, math.nan])
            mat.append(row)
            continue
        for s in ("binpack", "spread"):
            durs, _, _, _ = by_ms.get((model, s), ([], [], None, None))
            mu, _ = mean_std(durs)
            if math.isfinite(mu):
                row.append((mu - base_mu) / base_mu * 100.0)
            else:
                row.append(math.nan)
        mat.append(row)
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(mat, cmap="RdYlGn_r", aspect="auto", vmin=-40, vmax=40)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Binpack vs default", "Spread vs default"])
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([m.upper() for m in models])
    for i in range(len(models)):
        for j in range(2):
            v = mat[i][j]
            t = "—" if not math.isfinite(v) else f"{v:+.1f}%"
            ax.text(j, i, t, ha="center", va="center", color="black", fontsize=11)
    ax.set_title("Mean pod duration: % change vs default\n(negative = faster than default)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="% Δ duration")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def write_summary_csv(
    path: Path,
    models: list[str],
    by_ms: dict[tuple[str, str], tuple[list[float], list[float], str | None, str | None]],
    latest: dict[tuple[str, str], tuple[str, Path]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "model",
                "strategy",
                "run_folder",
                "n_pods",
                "mean_duration_s",
                "std_duration_s",
                "mean_metric",
                "std_metric",
                "metric_name",
            ]
        )
        for model in models:
            for s in STRATEGIES:
                durs, vals, mname, _ = by_ms.get((model, s), ([], [], None, None))
                mu_d, sd_d = mean_std(durs)
                mu_v, sd_v = mean_std(vals)
                entry = latest.get((model, s))
                folder = entry[1].parent.name if entry else ""
                w.writerow(
                    [
                        model,
                        s,
                        folder,
                        len(durs),
                        f"{mu_d:.4f}" if math.isfinite(mu_d) else "",
                        f"{sd_d:.4f}" if math.isfinite(sd_d) else "",
                        f"{mu_v:.6g}" if math.isfinite(mu_v) else "",
                        f"{sd_v:.6g}" if math.isfinite(sd_v) else "",
                        mname or "",
                    ]
                )


def main() -> None:
    ap = argparse.ArgumentParser(description="Visualize scheduler experiments from runs/*/metrics.csv")
    ap.add_argument(
        "--runs-dir",
        type=Path,
        default=RUNS_DIR_DEFAULT,
        help="Directory containing run subfolders",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for PNG/CSV (default: <runs-dir>/plots)",
    )
    args = ap.parse_args()
    runs_dir: Path = args.runs_dir
    out_dir: Path = args.out_dir or (runs_dir / "plots")
    out_dir.mkdir(parents=True, exist_ok=True)

    latest = collect_latest_runs(runs_dir)
    if not latest:
        raise SystemExit(f"No metrics.csv found under {runs_dir}")

    models = sorted({m for (m, _) in latest.keys()})
    by_ms: dict[tuple[str, str], tuple[list[float], list[float], str | None, str | None]] = {}
    for key, (_, mpath) in latest.items():
        by_ms[key] = summarize_run(mpath)

    plot_duration_subplots(out_dir / "scheduler_duration_by_workload.png", models, by_ms)
    plot_heatmap_duration_pct(out_dir / "scheduler_duration_pct_vs_default.png", models, by_ms)

    metric_models = [m for m in models if m != "dlrm"]
    if metric_models:
        plot_metric_subplots(out_dir / "scheduler_metric_by_workload.png", metric_models, by_ms)

    write_summary_csv(out_dir / "summary_table.csv", models, by_ms, latest)

    print(f"Wrote plots and summary under {out_dir}")
    print(f"  - scheduler_duration_by_workload.png")
    print(f"  - scheduler_duration_pct_vs_default.png")
    if metric_models:
        print(f"  - scheduler_metric_by_workload.png")
    print(f"  - summary_table.csv")


if __name__ == "__main__":
    main()
