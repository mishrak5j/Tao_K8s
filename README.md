# Tao_K8s — Kubernetes Resource Management for ML Workloads

**Course:** CSC4311 — Cloud Computing (Spring 2026)
**Authors:** Kshitij Mishra & Adrit Ganeriwala

---

## What This Project Does

This project measures how different **Kubernetes scheduling strategies** affect the performance of **PyTorch ML workloads**. We deploy the same batch Jobs under three schedulers — **Default**, **Bin-pack**, and **Spread** — on a multi-node cluster and compare wall-clock time, resource contention, and pod placement.

The repo includes everything needed to reproduce the experiments: Docker images, Kubernetes manifests, an automated experiment runner, and visualization scripts.

---

## Key Findings

After running 12 experiments (4 models × 3 strategies, 10 pods each) on GKE:

| Model | Default | Binpack | Spread | Binpack vs Default | Spread vs Default |
|:------|--------:|--------:|-------:|:------------------:|:-----------------:|
| **BERT** | 172.5s | 185.4s | 109.0s | +7.5% slower | **-36.8% faster** |
| **DLRM** | 72.5s | 60.1s | 66.4s | -17.1% faster | -8.5% faster |
| **ResNet** | 181.0s | 193.0s | 143.2s | +6.6% slower | **-20.9% faster** |
| **YOLO** | 30.3s | 19.9s | 13.7s | -34.2% faster | **-54.6% faster** |

1. **The Binpack Penalty:** Packing compute-heavy Transformers (BERT) onto shared nodes introduces a **~7.5% latency penalty** and high variance due to L3 cache contention.
2. **The Spread Advantage:** Isolating workloads guarantees predictability. For lightweight inference (YOLO), Spread scheduling improved performance by **54.6%** over the Default scheduler.
3. **No "Perfect" Scheduler:** Teams must map workloads on a cost-vs-throughput Pareto frontier to determine the correct heuristic for their SLA.

---

## Table of Contents

- [Key Findings](#key-findings)
- [How It Works](#how-it-works)
- [ML Workloads](#ml-workloads)
- [Scheduling Strategies Explained](#scheduling-strategies-explained)
- [Prerequisites](#prerequisites)
- [Setup — Minikube (Local)](#setup--minikube-local)
- [Setup — GKE (Cloud)](#setup--gke-cloud)
- [Running Experiments](#running-experiments)
- [Understanding the Output](#understanding-the-output)
- [Visualizing Results](#visualizing-results)
- [Documentation Site](#documentation-site)
- [Makefile Reference](#makefile-reference)
- [Troubleshooting](#troubleshooting)
- [References](#references)

---

## How It Works

The experiment pipeline has four stages:

```
1. BUILD           2. DEPLOY              3. RUN                   4. ANALYZE
─────────────      ─────────────          ─────────────            ─────────────
Docker image  ──>  Apply Job to     ──>   Pods execute       ──>  Collect logs,
with PyTorch       Kubernetes with        PyTorch benchmark        parse metrics,
benchmarks         chosen scheduler       in parallel              generate charts
```

In detail:

1. **Build** a Docker image containing all four PyTorch benchmarks (`make build`)
2. **Deploy** a Kubernetes batch Job using one of three schedulers. The Job runs N pods in parallel, each executing the same benchmark.
3. **Collect** logs from every pod after the Job finishes. Parse `TASK_NAME`, `METRIC`, `VALUE`, and `TOTAL_DURATION_SECONDS` from the output.
4. **Compare** results across schedulers using the visualization script.

`run_experiment.py` automates steps 2–3. `scripts/visualize_runs.py` handles step 4.

---

## ML Workloads

All four benchmarks use the same entrypoint:

```bash
python src/run_task.py --task {resnet,bert,yolo,dlrm}
```

| Task | What It Benchmarks | How |
|:---|:---|:---|
| **resnet** | Memory bandwidth | Runs ResNet-50 training steps (40 steps, batch size 8, 224x224 images) |
| **bert** | CPU compute and cache | Runs BERT-Base forward + backward passes (30 steps, batch size 4, seq len 128) |
| **yolo** | Inference latency | Runs YOLOv8n detection on random frames (25 runs after 5 warmup) |
| **dlrm** | Memory and I/O | Runs a mini DLRM with 26 embedding tables through forward + backward (50 steps, batch 2048) |

Each benchmark prints a standardized result block at the end:

```
TASK_NAME=resnet
METRIC=avg_step_time_sec
VALUE=0.8234
TOTAL_DURATION_SECONDS=32.9360
```

This format is what `run_experiment.py` parses to build `metrics.csv`.

---

## Scheduling Strategies Explained

All three schedulers run as separate processes in the cluster. Jobs select which scheduler places their pods via the `schedulerName` field.

### Default (`kube-scheduler`)

The built-in Kubernetes scheduler. Balances pods across nodes using a mix of heuristics. This is the **baseline** — every experiment compares against it.

No extra setup needed. Every cluster has this.

### Bin-pack (`binpack-scheduler`)

A secondary `kube-scheduler` instance configured with **`MostAllocated`** scoring. It prefers nodes that already have the most resources used, packing pods tightly onto fewer nodes.

**Effect:** Higher node utilization, but pods compete for CPU/memory on the same node. Good for cost (fewer nodes needed), bad for tail latency.

### Spread (`spread-scheduler`)

A secondary `kube-scheduler` instance configured with **`LeastAllocated`** scoring. It prefers nodes with the most free resources, spreading pods across the cluster.

**Effect:** Better isolation between pods, but uses more nodes. Good for predictable latency, worse for cost efficiency.

Both secondary schedulers are deployed as Deployments in `kube-system` with `leaderElection: false` (so they don't fight the default scheduler for the leader lease).

### Strategy Comparison

| Feature | Default | Binpack | Spread |
|:--------|:--------|:--------|:-------|
| **Primary Goal** | Balanced Load | Cluster Density | Pod Isolation |
| **Speed** | Medium | Slowest | **Fastest** |
| **Consistency** | Variable | High Jitter | **Deterministic** |
| **Cost Efficiency** | Medium | **Highest** | Lowest |
| **Best For** | General Purpose | Batch Processing | Real-time Inference |

---

## Prerequisites

| Requirement | Why |
|:---|:---|
| [Docker](https://docs.docker.com/get-docker/) | Build the benchmark container image |
| [kubectl](https://kubernetes.io/docs/tasks/tools/) | Interact with the Kubernetes cluster |
| [Minikube](https://minikube.sigs.k8s.io/docs/start/) **or** a GKE cluster | Run the cluster |
| Python 3.10+ | Run `run_experiment.py` and `visualize_runs.py` |
| matplotlib (`pip install -r requirements-experiments.txt`) | Generate charts (optional — CSV and logs work without it) |

---

## Setup — Minikube (Local)

### Step 1: Start a multi-node cluster

Bin-pack vs spread only matters with 2+ nodes. The default is 2 nodes with 4 CPUs and 6 GB RAM:

```bash
make setup
```

To use more nodes:

```bash
MINIKUBE_NODES=3 make setup
```

This also enables the `metrics-server` addon.

### Step 2: Build and load the Docker image

```bash
make build    # builds ml-workload:v1
make load     # loads the image into Minikube's container runtime
```

### Step 3: Create the namespace and quotas

```bash
kubectl apply -f k8s/00-namespace-quota.yaml
```

This creates:
- Namespace `ml-scheduling`
- ResourceQuota: max 4 CPU requests, 5 Gi memory requests, 20 pods
- LimitRange: default 100m CPU request, 500m CPU limit per container

### Step 4: Run your first experiment

```bash
make experiment MODEL=resnet STRATEGY=default
```

That's it. Results appear in `runs/`.

### Quick smoke test (no cluster needed)

Just test that the Docker image works:

```bash
make build
make run-bench-resnet
```

---

## Setup — GKE (Cloud)

### Step 1: Configure GCP variables

```bash
cp gcp.env.example gcp.env
```

Edit `gcp.env` with your project ID, region, Artifact Registry repo name, and cluster name:

```
GCP_PROJECT=your-gcp-project-id
GCP_REGION=us-central1
AR_REPO=ml-repo
GCP_CLUSTER=tao-cluster
```

### Step 2: Build, push, and deploy

```bash
make gcp-phase2
```

This single command:
1. Builds the Docker image
2. Tags and pushes it to Artifact Registry
3. Gets `kubectl` credentials for your GKE cluster
4. Applies the namespace, quotas, and YOLO batch Jobs via Kustomize overlay

Or run each step individually:

```bash
make gcp-push              # build + push to Artifact Registry
make gcp-get-credentials   # configure kubectl for GKE
make gcp-apply-workloads   # apply Kustomize overlay
```

### Step 3: Install secondary schedulers (if needed)

```bash
make install-secondary-scheduler
```

### Step 4: Run experiments with your registry image

```bash
python3 run_experiment.py \
  --model resnet \
  --strategy binpack \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT/ml-repo/ml-workload:v1 \
  --image-pull-policy Always
```

---

## Running Experiments

### Basic usage

```bash
python3 run_experiment.py --model <MODEL> --strategy <STRATEGY>
```

**Models:** `resnet`, `bert`, `yolo`, `dlrm`
**Strategies:** `default`, `binpack`, `spread`

### What the script does

1. **Cleanup** — Deletes any existing Jobs and Pods in the `ml-scheduling` namespace
2. **Scheduler setup** — If strategy is `binpack` or `spread`, applies the secondary scheduler manifests and waits for them to be ready
3. **Render Job** — Fills in `k8s/scheduling/experiment-template.yaml` with the model's CPU/memory profile and the chosen scheduler
4. **Apply and wait** — Creates the Job and polls until all pods complete (default timeout: 1 hour)
5. **Collect logs** — Fetches logs from every pod and parses the result block
6. **Write output** — Saves `metrics.csv`, `raw_logs.txt`, `latency_chart.png`, and the applied manifest
7. **Teardown** — Deletes the Job (unless `--skip-teardown`)

### Default batch profiles

Each model has a preset CPU/memory profile (can be overridden with `--completions` and `--parallelism`):

| Model | Completions | Parallelism | CPU Request | CPU Limit | Mem Request | Mem Limit |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| yolo | 10 | 5 | 500m | 1000m | 512Mi | 1024Mi |
| dlrm | 10 | 5 | 200m | 500m | 512Mi | 1024Mi |
| resnet | 10 | 5 | 800m | 1500m | 1024Mi | 2048Mi |
| bert | 10 | 5 | 1000m | 2000m | 2Gi | 4Gi |

### All CLI flags

| Flag | Default | Description |
|:---|:---|:---|
| `--model` | *(required)* | Workload: `resnet`, `bert`, `yolo`, `dlrm` |
| `--strategy` | *(required)* | Scheduler: `default`, `binpack`, `spread` |
| `--namespace` | `ml-scheduling` | Kubernetes namespace |
| `--image` | `ml-workload:v1` | Container image |
| `--image-pull-policy` | `Never` | `Never` (Minikube), `IfNotPresent`, or `Always` (GKE) |
| `--completions` | from profile | Override number of pod completions |
| `--parallelism` | from profile | Override max parallel pods |
| `--wait-timeout` | `3600` | Seconds to wait for Job to finish |
| `--skip-cleanup` | off | Don't delete existing Jobs before starting |
| `--skip-teardown` | off | Leave the Job running after collecting metrics |

### Makefile shortcut

```bash
make experiment MODEL=yolo STRATEGY=spread
```

---

## Understanding the Output

Each run creates a timestamped folder under `runs/`:

```
runs/20260412T044014Z_resnet_binpack/
├── manifest-applied.yaml   # The exact Job YAML that was applied
├── metrics.csv             # One row per pod with parsed log fields
├── raw_logs.txt            # Full container logs from every pod
└── latency_chart.png       # Bar chart of per-pod duration
```

### metrics.csv columns

| Column | Example | Description |
|:---|:---|:---|
| `run_id` | `20260412T044014Z` | UTC timestamp of the run |
| `job` | `ml-exp-resnet-bp-0412044014` | Kubernetes Job name |
| `pod` | `ml-exp-resnet-bp-…-abc12` | Pod name |
| `strategy` | `binpack` | Scheduler used |
| `task_name` | `resnet` | Benchmark that ran |
| `metric` | `avg_step_time_sec` | Workload-specific metric name |
| `value` | `0.8234` | Metric value |
| `total_duration_seconds` | `32.936` | Total wall-clock time for that pod |

The `runs/` directory is **gitignored** (the folder is kept via `runs/.gitkeep`).

---

## Visualizing Results

After running experiments across multiple models and strategies, generate comparison charts.

### Basic charts

```bash
python3 scripts/visualize_runs.py
```

Scans `runs/*/metrics.csv`, picks the **latest** run for each `(model, strategy)` pair, and writes to `runs/plots/`:

| File | What it shows |
|:---|:---|
| `scheduler_duration_by_workload.png` | Mean pod duration ± std dev for each workload, grouped by scheduler. Includes `+X%` annotations vs default. |
| `scheduler_duration_pct_vs_default.png` | Heatmap showing how much slower or faster bin-pack and spread are compared to default (per workload). |
| `scheduler_metric_by_workload.png` | Mean workload-specific metric ± std dev. DLRM is excluded (its loss metric is numerically unstable). |
| `summary_table.csv` | Raw aggregated numbers: mean duration, std, mean metric, source run folder. |

### Presentation-quality charts

```bash
python3 scripts/visualize_presentation.py
# or: make visualize-presentation
```

Generates four publication-ready visualizations at 200 DPI:

| File | What it shows |
|:---|:---|
| `grouped_bar_mean_latency.png` | **Performance Baseline** — Single grouped bar chart with all 4 models × 3 strategies, error bars, and value annotations. |
| `boxplot_duration_jitter.png` | **Predictability Analysis** — 2×2 box-and-whisker plots showing per-pod duration distribution with overlaid data points. Reveals jitter and "noisy neighbor" effects. |
| `heatmap_pct_change.png` | **Scheduling Penalty** — Heatmap of % change vs Default baseline with faster/slower annotations. Headlines like "Binpack is +7.5% slower on BERT." |
| `pareto_scatter.png` | **Pareto Frontier** — Throughput (pods/min) vs resource-time cost scatter plot. Each point is one (model, strategy) combination with strategy colors and model shapes. |

Both scripts accept `--runs-dir` and `--out-dir` flags:

```bash
python3 scripts/visualize_presentation.py --runs-dir /path/to/runs --out-dir /path/to/output
```

---

## Documentation Site

The project includes a full documentation site:

- **Standalone HTML:** Open `docs/index.html` in a browser for a single-page reference with all sections, live experiment data, and embedded chart images.
- **MkDocs Material:** Run the mkdocs site locally for a multi-page documentation experience:

```bash
pip install mkdocs-material
mkdocs serve
```

The mkdocs site includes pages for architecture, analytics/results, and operational runbooks. Configuration is in `mkdocs.yml`.

---

## Makefile Reference

| Command | What it does |
|:---|:---|
| `make setup` | Start Minikube (2 nodes, 4 CPU, 6 GB). Override: `MINIKUBE_NODES=3 make setup` |
| `make build` | Build CPU Docker image (`ml-workload:v1`) |
| `make build-gpu` | Build GPU Docker image (`ml-workload-gpu:v1`) |
| `make load` | Load image into Minikube |
| `make smoke` | Build + run all 4 benchmarks in Docker (no cluster) |
| `make run-bench-resnet` | Run just ResNet in Docker (no cluster) |
| `make run` | Run ResNet + default scheduler experiment |
| `make experiment` | Run experiment with `MODEL` and `STRATEGY` variables |
| `make visualize-presentation` | Generate 4 presentation-quality charts from experiment runs |
| `make install-secondary-scheduler` | Deploy bin-pack + spread schedulers to kube-system |
| `make uninstall-secondary-scheduler` | Remove secondary schedulers |
| `make install-volcano` | Install Volcano gang-scheduling controllers |
| `make gcp-phase2` | Full GKE deploy: build, push, credentials, apply overlay |
| `make gcp-push` | Build + push image to Artifact Registry |
| `make gcp-get-credentials` | Configure kubectl for GKE cluster |
| `make gcp-apply-workloads` | Apply Kustomize overlay to GKE |
| `make clean-jobs` | Delete all Jobs in ml-scheduling namespace |
| `make clean` | Delete all Jobs + destroy Minikube cluster |
| `make lint` | Run flake8 on src/ |
| `make lint-fix` | Run black formatter on src/ |

---

## Troubleshooting

### Secondary scheduler pods are in CrashLoopBackOff

The `kube-scheduler` image tag must match your cluster's Kubernetes minor version:

```bash
kubectl version -o json | jq -r '.serverVersion.gitVersion'
# e.g. v1.35.1 → use kube-scheduler:v1.35.0
```

Edit the `image:` line in `k8s/scheduling/secondary-scheduler-binpack.yaml` and `secondary-scheduler-spread.yaml`, then re-apply.

### Pods stuck in Pending

1. Check events: `kubectl get events -n ml-scheduling`
2. Check scheduler logs: `kubectl logs -n kube-system deploy/second-scheduler-binpack`
3. Check quota: `kubectl describe resourcequota -n ml-scheduling`
4. If quota is exceeded, reduce `--parallelism` or `--completions`

### OOMKilled pods

The BERT benchmark needs ~4 Gi memory limit. If pods are OOMKilled, check that the namespace LimitRange and ResourceQuota allow enough memory, and that your nodes have sufficient capacity.

### Image pull errors on Minikube

After `make load`, the image is inside Minikube. Jobs must use `imagePullPolicy: Never` (this is the default in `run_experiment.py`). If you see `ErrImagePull`, verify:

```bash
minikube image ls | grep ml-workload
```

---

## References

- [Kubernetes Scheduler Configuration](https://kubernetes.io/docs/reference/scheduling/config/)
- [Volcano — Gang Scheduling](https://volcano.sh/)
- [PyTorch](https://pytorch.org/)
- [Minikube](https://minikube.sigs.k8s.io/)
- [Google Kubernetes Engine](https://cloud.google.com/kubernetes-engine/docs)
