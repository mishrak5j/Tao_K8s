# Kubernetes resource management for ML workloads

**Course:** CSC4311 — Cloud Computing (Spring 2026)  
**Author:** Kshitij Mishra

## Workloads

Four **PyTorch** benchmarks run via a single entrypoint:

```bash
python src/run_task.py --task {resnet,bert,yolo,dlrm}
```

| Task | Script module | Role |
|------|-----------------|------|
| `resnet` | `bench_resnet.py` | ResNet-50 training steps |
| `bert` | `bench_bert.py` | BERT-Base–sized transformer (random init) |
| `yolo` | `bench_yolo.py` | YOLOv8n inference latency |
| `dlrm` | `bench_dlrm.py` | Mini DLRM-style embeddings + MLP |

Logs use `task_common.print_result` (`TASK_NAME=`, `TOTAL_DURATION_SECONDS=`).

## Images

- **`Dockerfile`** — CPU PyTorch (`make build` → `ml-workload:v1`)
- **`Dockerfile.gpu`** — CUDA base for GKE/Linux GPU (`make build-gpu`)

Dependencies: `requirements.txt` (torch installed in Dockerfile; transformers, ultralytics, numpy).

## Scheduling (only four methods)

The repo is scoped to **default**, **bin packing**, **spread**, and **gang** scheduling. All Job manifests live under **`k8s/scheduling/`**. See [`k8s/scheduling/README.md`](k8s/scheduling/README.md) for apply order and manifests.

```bash
make install-secondary-scheduler   # bin-pack + spread (secondary kube-schedulers)
make install-volcano               # gang (Volcano)
```

## Phase 2 — GKE + Artifact Registry

With APIs enabled, a Docker Artifact Registry repo, and a running cluster:

1. **Optional:** `cp gcp.env.example gcp.env` and edit if your project or cluster name differs. The Makefile loads `gcp.env` automatically.
2. **One-shot:** from the repo root, `make gcp-phase2` — builds the image, tags and pushes to `$(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/$(AR_REPO)/ml-workload:$(TAG)`, runs `gcloud container clusters get-credentials` for `$(GCP_CLUSTER)`, and applies the namespace plus all Job manifests with the correct image (via `k8s/overlays/gke`).

Or run steps separately: `make gcp-push`, then `make gcp-get-credentials`, then `make gcp-apply-workloads`.

**After apply:** install secondary schedulers or Volcano as needed (`make install-secondary-scheduler`, `make install-volcano`), then re-apply or create Jobs per [`k8s/scheduling/README.md`](k8s/scheduling/README.md). The default kube-scheduler Job is `ml-sched-default-resnet`.

**Note:** A single **e2-medium** node is tight for PyTorch; for heavier runs use a larger machine type or more nodes. The Volcano gang Job requests two replicas (`minAvailable: 2`); ensure the cluster can place both pods.

## Cluster workflow (Minikube)

**Minikube:** After `make load`, set Jobs back to `image: ml-workload:v1` and `imagePullPolicy: Never` (see comments in those YAML files), or maintain a local overlay.

**GKE (manual image line):** You can still edit `k8s/scheduling/*.yaml` by hand, or use only the overlay above so you never commit project-specific URLs.

```bash
make setup
make build
make load
kubectl apply -f k8s/00-namespace-quota.yaml
make run    # default scheduler + ResNet Job
kubectl logs -n ml-scheduling job/ml-sched-default-resnet
```

Local Docker smoke (no cluster):

```bash
make build
make run-bench-resnet
```

## References

- [Kubernetes scheduler configuration](https://kubernetes.io/docs/reference/scheduling/config/)
- [Volcano](https://volcano.sh/)
