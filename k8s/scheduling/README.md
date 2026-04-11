# Four scheduling methods

| Method | What installs it | Job manifest |
|--------|-------------------|--------------|
| **Default** | Built-in cluster `kube-scheduler` (nothing extra) | `job-scheduler-default.yaml` |
| **Bin packing** | `make install-secondary-scheduler` | `job-scheduler-binpack.yaml` |
| **Spread** | Same as bin packing | `job-scheduler-spread.yaml` |
| **Gang** | `make install-volcano` | `job-volcano-gang.yaml` |

Supporting YAML (not Jobs): `secondary-scheduler-rbac.yaml`, `secondary-scheduler-binpack.yaml`, `secondary-scheduler-spread.yaml`.

## Image and pull policy (GKE vs Minikube)

Job manifests use a **GCP Artifact Registry** placeholder:

`us-central1-docker.pkg.dev/YOUR_PROJECT/YOUR_REPO/ml-workload:v1` with **`imagePullPolicy: IfNotPresent`**.

**Recommended on GKE:** from the repo root, set `GCP_PROJECT`, `GCP_REGION`, `AR_REPO` (see `gcp.env.example`), then `make gcp-push` and `make gcp-apply-workloads` — the overlay `k8s/overlays/gke` rewrites all Job images via Kustomize (see root `README.md`, Phase 2).

Alternatively:

1. Build and push: `docker tag …` / `docker push` to your repo (often `REGION-docker.pkg.dev/PROJECT/REPO/ml-workload:v1`).
2. Replace `YOUR_PROJECT` / `YOUR_REPO` (and `us-central1` if your region differs) in every Job YAML, **or** use `sed`/Kustomize.
3. Ensure nodes can pull (same GCP project as Artifact Registry is usually enough; private repos may need `imagePullSecrets`).

**Minikube** (image only on the node after `make load`): set `image: ml-workload:v1` and `imagePullPolicy: Never` in these Job files, then apply.

## Apply order

1. `kubectl apply -f k8s/00-namespace-quota.yaml`
2. Build and push the image (GKE) **or** `make build` + `make load` (Minikube) and fix image lines as above
3. **Default:** `kubectl apply -f k8s/scheduling/job-scheduler-default.yaml`
4. **Bin pack / spread:** `make install-secondary-scheduler`, wait until both scheduler Deployments are Running in `kube-system`, then apply `job-scheduler-binpack.yaml` or `job-scheduler-spread.yaml`
5. **Gang:** `make install-volcano`, wait for controllers, then `kubectl apply -f k8s/scheduling/job-volcano-gang.yaml`

## kube-scheduler image

Edit the image tag in `secondary-scheduler-binpack.yaml` and `secondary-scheduler-spread.yaml` to match your cluster minor version if pods crash.

## Uninstall schedulers

- `make uninstall-secondary-scheduler`
- Volcano: `kubectl delete -f` the same URL used in `make install-volcano` (dev clusters only; CRDs affect the whole cluster)
