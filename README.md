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

## Cluster workflow

**GKE:** Push `ml-workload` to Artifact Registry, replace the placeholder image in `k8s/scheduling/*.yaml` with your `REGION-docker.pkg.dev/...` URL (`imagePullPolicy: IfNotPresent` is already set). Configure pull auth if the repo is private.

**Minikube:** After `make load`, set Jobs back to `image: ml-workload:v1` and `imagePullPolicy: Never` (see comments in those YAML files), or maintain a local overlay.

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
