# Scheduling manifests

## What is in this directory

| Piece | Role |
|-------|------|
| **`experiment-template.yaml`** | Template for [`run_experiment.py`](../../run_experiment.py); not applied directly—placeholders are substituted per run. |
| **`secondary-scheduler-rbac.yaml`**, **`secondary-scheduler-binpack.yaml`**, **`secondary-scheduler-spread.yaml`** | RBAC + Deployments for bin-pack and spread **secondary kube-schedulers** (`make install-secondary-scheduler`). |
| **`job-scheduler-binpack-yolo-batch.yaml`** | Optional manual YOLO batch Job using the binpack scheduler. |
| **`job-spread-yolo-batch.yaml`** | Optional manual YOLO batch Job using the spread scheduler. |
| **`job-dlrm-binpack.yaml`** | Optional manual DLRM batch Job using the binpack scheduler. |

**Schedulers:**

| Strategy | What you need |
|----------|----------------|
| **Default** | Cluster `kube-scheduler` only — use `run_experiment.py --strategy default` or a Job without `schedulerName`. |
| **Bin pack** | `make install-secondary-scheduler`, then Jobs with `schedulerName: binpack-scheduler` (set by the experiment script for `--strategy binpack`). |
| **Spread** | Same install as bin pack; Jobs use `schedulerName: spread-scheduler` (`--strategy spread`). |

**Volcano:** `make install-volcano` installs controllers; **no sample Volcano Job** lives in this folder. Add your own manifests if you use gang scheduling.

Supporting YAML (not Jobs): `secondary-scheduler-rbac.yaml`, `secondary-scheduler-binpack.yaml`, `secondary-scheduler-spread.yaml`. Re-apply RBAC after edits: `kubectl apply -f k8s/scheduling/secondary-scheduler-rbac.yaml` and restart the two scheduler Deployments.

## Image and pull policy (GKE vs Minikube)

Manual Job YAMLs may use a **GCP Artifact Registry** placeholder:

`us-central1-docker.pkg.dev/YOUR_PROJECT/YOUR_REPO/ml-workload:v1` with **`imagePullPolicy: IfNotPresent`**.

**Recommended on GKE:** from the repo root, set `GCP_PROJECT`, `GCP_REGION`, `AR_REPO` (see `gcp.env.example`), then `make gcp-push` and `make gcp-apply-workloads` — the overlay [`k8s/overlays/gke`](../../k8s/overlays/gke) rewrites Job images via Kustomize (see root `README.md`, Phase 2). The overlay currently includes the **YOLO batch Jobs** plus namespace/quota.

Alternatively:

1. Build and push: `docker tag …` / `docker push` to your repo (often `REGION-docker.pkg.dev/PROJECT/REPO/ml-workload:v1`).
2. Replace `YOUR_PROJECT` / `YOUR_REPO` (and `us-central1` if your region differs) in every Job YAML, **or** use `sed`/Kustomize.
3. Ensure nodes can pull (same GCP project as Artifact Registry is usually enough; private repos may need `imagePullSecrets`).

**Minikube** (image only on the node after `make load`): use `image: ml-workload:v1` and `imagePullPolicy: Never`, or run `run_experiment.py` with defaults.

## Apply order (recommended)

1. `kubectl apply -f k8s/00-namespace-quota.yaml`
2. Build and push the image (GKE) **or** `make build` + `make load` (Minikube).
3. **Automated path:** from the repo root, run [`run_experiment.py`](../../run_experiment.py) (see root `README.md`). For `binpack` / `spread`, the script applies the secondary scheduler manifests and waits for them to be ready.
4. **Manual Jobs:** if not using the script, run `make install-secondary-scheduler` when using binpack/spread, wait until both scheduler Deployments are **Running** in `kube-system`, then `kubectl apply -f` the desired Job YAML (e.g. YOLO or DLRM batch files above).

## kube-scheduler image

The secondary scheduler Deployments use `registry.k8s.io/kube-scheduler` with a tag that **must match your API server minor version** (Kubernetes version skew). If those pods are **`Error` / CrashLoopBackOff**, bump or lower the tag to match:

```bash
kubectl version -o json | jq -r '.serverVersion.gitVersion'   # e.g. v1.35.1 → use kube-scheduler:v1.35.0
```

Or copy the image from the control-plane scheduler:

```bash
kubectl get pods -n kube-system -o jsonpath='{range .items[*]}{.spec.containers[*].image}{"\n"}{end}' | grep kube-scheduler
```

Then edit the `image:` line in `secondary-scheduler-binpack.yaml` and `secondary-scheduler-spread.yaml` and re-apply.

The embedded `KubeSchedulerConfiguration` sets **`leaderElection.leaderElect: false`**. The scheduler API defaults leader election to **on**; without that block, secondary schedulers can fight the default `kube-scheduler` for the same lease and exit immediately (`Error` / `CrashLoopBackOff`).

The scheduler image’s **ENTRYPOINT is `/go-runner`**; set **`command: ["/usr/local/bin/kube-scheduler"]`** so `--config` is passed to the real binary (otherwise you see `flag provided but not defined: -config` from go-runner).

If pods stay **Pending** and **`kubectl describe pod` shows empty Events**, also run **`kubectl get events -n ml-scheduling --field-selector involvedObject.name=<pod-name>`** (events are not always shown in `describe`). Check **`kubectl logs -n kube-system deploy/second-scheduler-binpack`** for scheduling errors.

## Uninstall schedulers

- `make uninstall-secondary-scheduler`
- Volcano: `kubectl delete -f` the same URL used in `make install-volcano` (dev clusters only; CRDs affect the whole cluster)
