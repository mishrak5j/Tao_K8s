#!/usr/bin/env python3
"""
Automated benchmark control loop: deploy → wait → collect → analyze → teardown.

Reads k8s/scheduling/experiment-template.yaml and applies a Batch Job with the
chosen model profile and scheduler strategy.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Optional chart (fail with clear message if missing)
try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover
    plt = None

REPO_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = REPO_ROOT / "k8s/scheduling/experiment-template.yaml"
SCHEDULING_DIR = REPO_ROOT / "k8s/scheduling"
RUNS_DIR = REPO_ROOT / "runs"

# Presets for batch Jobs (see k8s/scheduling/experiment-template.yaml).
PROFILES: dict[str, dict[str, str | int]] = {
    "yolo": {
        "completions": 10,
        "parallelism": 5,
        "cpu_request": "500m",
        "cpu_limit": "1000m",
        "mem_request": "512Mi",
        "mem_limit": "1024Mi",
    },
    "dlrm": {
        "completions": 10,
        "parallelism": 5,
        "cpu_request": "200m",
        "cpu_limit": "500m",
        "mem_request": "512Mi",
        "mem_limit": "1024Mi",  # fixed from 512Mi to prevent OOM
    },
    "resnet": {
        "completions": 10,
        "parallelism": 5,
        "cpu_request": "800m",
        "cpu_limit": "1500m",
        "mem_request": "1024Mi",
        "mem_limit": "2048Mi",
    },
    "bert": {
        "completions": 10,
        "parallelism": 5,
        "cpu_request": "1000m",
        "cpu_limit": "2000m",
        "mem_request": "2Gi",
        "mem_limit": "4Gi",  # BERT is memory-heavy; needs more room
    },
}

STRATEGY_SCHEDULER = {
    "default": None,
    "binpack": "binpack-scheduler",
    "spread": "spread-scheduler",
}

SECONDARY_MANIFESTS = (
    "secondary-scheduler-rbac.yaml",
    "secondary-scheduler-binpack.yaml",
    "secondary-scheduler-spread.yaml",
)


def kubectl(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *args],
        check=check,
        text=True,
        capture_output=True,
    )


def kubectl_json(args: list[str]) -> dict:
    p = kubectl(args, check=False)
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout or "kubectl failed")
    return json.loads(p.stdout)


def kubectl_apply_file(path: Path) -> None:
    p = kubectl(["apply", "-f", str(path)], check=False)
    if p.returncode != 0:
        raise RuntimeError(p.stderr or p.stdout or f"kubectl apply failed: {path}")


def preflight_cleanup(namespace: str) -> None:
    kubectl(["delete", "jobs", "-n", namespace, "--all", "--ignore-not-found"], check=False)
    kubectl(["delete", "pods", "-n", namespace, "--all", "--ignore-not-found"], check=False)
    deadline = time.time() + 120
    while time.time() < deadline:
        p = kubectl(
            ["get", "pods", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"],
            check=False,
        )
        if p.returncode == 0 and not (p.stdout or "").strip():
            return
        time.sleep(1)


def ensure_secondary_schedulers() -> None:
    for name in SECONDARY_MANIFESTS:
        path = SCHEDULING_DIR / name
        if not path.is_file():
            raise FileNotFoundError(path)
        kubectl_apply_file(path)
    for deploy in ("second-scheduler-binpack", "second-scheduler-spread"):
        p = kubectl(
            [
                "rollout",
                "status",
                f"deployment/{deploy}",
                "-n",
                "kube-system",
                "--timeout=180s",
            ],
            check=False,
        )
        if p.returncode != 0:
            raise RuntimeError(
                f"Scheduler deployment {deploy} not ready: {p.stderr or p.stdout}"
            )


def scheduler_line(strategy: str) -> str:
    name = STRATEGY_SCHEDULER[strategy]
    if name is None:
        return ""
    return f"      schedulerName: {name}\n"


def make_job_name(model: str, strategy: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%m%d%H%M%S")
    strat_short = {"default": "def", "binpack": "bp", "spread": "spr"}[strategy]
    base = f"ml-exp-{model}-{strat_short}-{ts}"
    base = base.lower()
    base = re.sub(r"[^a-z0-9-]", "-", base)
    return base[:63].strip("-")


def render_template(
    *,
    job_name: str,
    namespace: str,
    profile: dict[str, str | int],
    task: str,
    image: str,
    image_pull_policy: str,
    strategy: str,
) -> str:
    raw = TEMPLATE_PATH.read_text()
    repl = {
        "__JOB_NAME__": job_name,
        "__NAMESPACE__": namespace,
        "__COMPLETIONS__": str(profile["completions"]),
        "__PARALLELISM__": str(profile["parallelism"]),
        "__IMAGE__": image,
        "__IMAGE_PULL_POLICY__": image_pull_policy,
        "__TASK__": task,
        "__CPU_REQUEST__": str(profile["cpu_request"]),
        "__CPU_LIMIT__": str(profile["cpu_limit"]),
        "__MEM_REQUEST__": str(profile["mem_request"]),
        "__MEM_LIMIT__": str(profile["mem_limit"]),
        "__SCHEDULER_LINE__": scheduler_line(strategy),
    }
    for k, v in repl.items():
        raw = raw.replace(k, v)
    for token in repl:
        if token in raw:
            raise ValueError(f"template still contains unreplaced token: {token}")
    return raw


def quota_sanity_check(profile: dict[str, str | int]) -> None:
    """Warn if static sum of requests may exceed ml-compute-quota (4 CPU, 5Gi requests)."""
    try:
        c = int(str(profile["completions"]))
        pr = str(profile["cpu_request"]).rstrip("m")
        cpu_m = int(pr) if pr.isdigit() else 0
        if not cpu_m:
            return
        total_m = c * cpu_m
        if total_m > 4000:
            print(
                f"Warning: completions×cpu_request ≈ {total_m}m > 4000m namespace quota; "
                "Job may stay Pending.",
                file=sys.stderr,
            )
    except (ValueError, TypeError):
        pass


def wait_job_done(namespace: str, job_name: str, timeout_sec: int) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        data = kubectl_json(["get", "job", job_name, "-n", namespace, "-o", "json"])
        spec = data.get("spec") or {}
        status = data.get("status") or {}
        completions = int(spec.get("completions") or 1)
        succeeded = int(status.get("succeeded") or 0)
        failed = int(status.get("failed") or 0)
        if succeeded >= completions:
            return
        if failed > 0:
            raise RuntimeError(f"Job {job_name} has failed pods (failed={failed})")
        time.sleep(2)
    raise TimeoutError(f"Job {job_name} did not finish within {timeout_sec}s")


def list_job_pods(namespace: str, job_name: str) -> list[str]:
    data = kubectl_json(
        [
            "get",
            "pods",
            "-n",
            namespace,
            "-l",
            f"job-name={job_name}",
            "-o",
            "json",
        ]
    )
    items = data.get("items") or []
    names = [i.get("metadata", {}).get("name") for i in items]
    return sorted(n for n in names if n)


def pod_logs(namespace: str, pod: str) -> str:
    p = kubectl(["logs", "-n", namespace, pod, "-c", "ml-worker"], check=False)
    if p.returncode != 0:
        return f"<logs unavailable: {p.stderr or p.stdout}>"
    return p.stdout or ""


def parse_result_block(log: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in log.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, _, rest = line.partition("=")
        key, rest = key.strip(), rest.strip()
        if key:
            out[key] = rest
    return out


def write_raw_logs(path: Path, sections: list[tuple[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for title, body in sections:
            f.write(f"=== {title} ===\n")
            f.write(body)
            if not body.endswith("\n"):
                f.write("\n")
            f.write("\n")


def write_metrics_csv(
    path: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def build_chart(
    out_path: Path,
    labels: list[str],
    durations: list[float],
    values: list[float | None],
    metric_name: str | None,
) -> None:
    if plt is None:
        print(
            "matplotlib not installed; skip latency_chart.png (pip install -r requirements-experiments.txt)",
            file=sys.stderr,
        )
        return
    x = range(len(labels))
    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.bar([str(i) for i in x], durations, color="steelblue", alpha=0.85, label="TOTAL_DURATION_S")
    ax1.set_xlabel("Pod index")
    ax1.set_ylabel("TOTAL_DURATION_SECONDS")
    ax1.set_title("Benchmark run (per pod)")
    if values and any(v is not None for v in values) and metric_name:
        ax2 = ax1.twinx()
        ax2.plot(
            list(x),
            [v if v is not None else 0 for v in values],
            color="darkorange",
            marker="o",
            linestyle="--",
            label=metric_name,
        )
        ax2.set_ylabel(metric_name or "VALUE")
        lines1, lab1 = ax1.get_legend_handles_labels()
        lines2, lab2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, lab1 + lab2, loc="upper right")
    else:
        ax1.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser(description="Tao_K8s experiment control loop")
    p.add_argument("--model", required=True, choices=sorted(PROFILES), help="Workload / --task name")
    p.add_argument(
        "--strategy",
        required=True,
        choices=sorted(STRATEGY_SCHEDULER),
        help="default | binpack | spread",
    )
    p.add_argument("--namespace", default="ml-scheduling", help="Kubernetes namespace")
    p.add_argument("--image", default="ml-workload:v1", help="Container image")
    p.add_argument(
        "--image-pull-policy",
        default="Never",
        choices=["Never", "IfNotPresent", "Always"],
        help="Image pull policy (Never for Minikube after make load)",
    )
    p.add_argument("--completions", type=int, default=None, help="Override profile completions")
    p.add_argument("--parallelism", type=int, default=None, help="Override profile parallelism")
    p.add_argument(
        "--wait-timeout",
        type=int,
        default=3600,
        help="Seconds to wait for Job success",
    )
    p.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Do not delete jobs/pods before run (not recommended)",
    )
    p.add_argument(
        "--skip-teardown",
        action="store_true",
        help="Leave Job running after metrics collection",
    )
    args = p.parse_args()

    if not TEMPLATE_PATH.is_file():
        sys.exit(f"Missing template: {TEMPLATE_PATH}")

    profile = dict(PROFILES[args.model])
    if args.completions is not None:
        profile["completions"] = args.completions
    if args.parallelism is not None:
        profile["parallelism"] = args.parallelism

    quota_sanity_check(profile)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_name = make_job_name(args.model, args.strategy)
    out_dir = RUNS_DIR / f"{run_id}_{args.model}_{args.strategy}"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_cleanup:
        print("Preflight: deleting existing Jobs and Pods in namespace…")
        preflight_cleanup(args.namespace)

    if args.strategy in ("binpack", "spread"):
        print("Ensuring secondary schedulers (kube-system)…")
        ensure_secondary_schedulers()

    manifest = render_template(
        job_name=job_name,
        namespace=args.namespace,
        profile=profile,
        task=args.model,
        image=args.image,
        image_pull_policy=args.image_pull_policy,
        strategy=args.strategy,
    )
    manifest_path = out_dir / "manifest-applied.yaml"
    manifest_path.write_text(manifest, encoding="utf-8")

    print(f"Applying Job {job_name}…")
    kubectl_apply_file(manifest_path)

    print("Waiting for Job to complete…")
    try:
        wait_job_done(args.namespace, job_name, args.wait_timeout)
    except (TimeoutError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)

    pods = list_job_pods(args.namespace, job_name)
    sections: list[tuple[str, str]] = []
    rows: list[dict[str, str]] = []
    durations: list[float] = []
    val_floats: list[float | None] = []
    metric_names: list[str | None] = []

    for pod in pods:
        log = pod_logs(args.namespace, pod)
        sections.append((f"pod/{pod}", log))
        parsed = parse_result_block(log)
        task_name = parsed.get("TASK_NAME", "")
        metric = parsed.get("METRIC", "")
        value_str = parsed.get("VALUE", "")
        dur_str = parsed.get("TOTAL_DURATION_SECONDS", "")
        try:
            dur_f = float(dur_str) if dur_str else float("nan")
        except ValueError:
            dur_f = float("nan")
        vf: float | None
        try:
            vf = float(value_str) if value_str else None
        except ValueError:
            vf = None

        rows.append(
            {
                "run_id": run_id,
                "job": job_name,
                "pod": pod,
                "strategy": args.strategy,
                "task_name": task_name,
                "metric": metric,
                "value": value_str,
                "total_duration_seconds": dur_str,
            }
        )
        durations.append(dur_f)
        val_floats.append(vf)
        metric_names.append(metric or None)

    raw_path = out_dir / "raw_logs.txt"
    write_raw_logs(raw_path, sections)

    fields = [
        "run_id",
        "job",
        "pod",
        "strategy",
        "task_name",
        "metric",
        "value",
        "total_duration_seconds",
    ]
    csv_path = out_dir / "metrics.csv"
    write_metrics_csv(csv_path, rows, fields)

    # Chart: bar = duration; optional line = VALUE if numeric and metric consistent
    labels = [f"{i}:{pods[i][-12:]}" for i in range(len(pods))] if pods else ["no-pods"]
    if not pods:
        durations = [0.0]
        val_floats = [None]
        metric_names = [None]

    primary_metric = next((m for m in metric_names if m), None)
    chart_path = out_dir / "latency_chart.png"
    build_chart(
        chart_path,
        labels,
        durations,
        val_floats,
        primary_metric,
    )

    if not args.skip_teardown:
        print(f"Deleting Job {job_name}…")
        kubectl(
            ["delete", "job", job_name, "-n", args.namespace, "--ignore-not-found"],
            check=False,
        )

    print(f"Done. Artifacts: {out_dir}")
    print(f"  {raw_path.name}, {csv_path.name}, {chart_path.name}")


if __name__ == "__main__":
    main()
