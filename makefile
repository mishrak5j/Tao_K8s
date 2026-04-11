-include gcp.env

# Variables (match k8s manifests)
IMAGE_NAME=ml-workload
TAG=v1
IMAGE_GPU=ml-workload-gpu
TAG_GPU=v1
CPUS=4
MEM=6144

# GKE / Artifact Registry (override via gcp.env or environment)
GCP_PROJECT ?= $(shell gcloud config get-value project 2>/dev/null)
GCP_REGION ?= us-central1
AR_REPO ?= ml-repo
GCP_CLUSTER ?= tao-cluster
AR_IMAGE ?= $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT)/$(AR_REPO)/$(IMAGE_NAME)

.PHONY: setup build load run lint lint-fix clean clean-jobs build-gpu run-gpu-resnet run-bench-resnet smoke \
	install-secondary-scheduler uninstall-secondary-scheduler install-volcano \
	gcp-kustomize gcp-push gcp-get-credentials gcp-apply-workloads gcp-phase2

# --- GKE Phase 2: push image + kubectl apply (after cluster and AR repo exist) ---
gcp-kustomize:
	@test -n "$(GCP_PROJECT)" || (echo "Set GCP_PROJECT or run: gcloud config set project YOUR_PROJECT"; exit 1)
	sed -e 's|@AR_IMAGE@|$(AR_IMAGE)|g' -e 's|@TAG@|$(TAG)|g' \
		k8s/overlays/gke/kustomization.yaml.in > k8s/overlays/gke/kustomization.yaml

gcp-push: build
	@test -n "$(GCP_PROJECT)" || (echo "Set GCP_PROJECT or run: gcloud config set project YOUR_PROJECT"; exit 1)
	docker tag $(IMAGE_NAME):$(TAG) $(AR_IMAGE):$(TAG)
	docker push $(AR_IMAGE):$(TAG)
	@echo "Pushed $(AR_IMAGE):$(TAG)"

# Regional GKE cluster (use --region; zonal clusters use --zone instead)
gcp-get-credentials:
	gcloud container clusters get-credentials $(GCP_CLUSTER) --region=$(GCP_REGION)

gcp-apply-workloads: gcp-kustomize
	kubectl kustomize --load-restrictor=LoadRestrictionsNone k8s/overlays/gke | kubectl apply -f -

# Full Phase 2: build, push to Artifact Registry, kubeconfig for GKE, apply namespace + Jobs
gcp-phase2: gcp-push gcp-get-credentials gcp-apply-workloads
	@echo "Next: kubectl get pods -n ml-scheduling; kubectl logs -n ml-scheduling job/ml-sched-default-resnet"

# 1. Start Minikube with metrics-server (use multiple nodes if you want placement variety)
setup:
	minikube start --driver=docker --cpus=$(CPUS) --memory=$(MEM)
	minikube addons enable metrics-server

# 2. Linting
lint:
	python3 -m pip install -q flake8
	python3 -m flake8 src/*.py

lint-fix:
	python3 -m pip install -q black
	python3 -m black src/*.py

# 3. Build the Docker image (CPU PyTorch benchmarks)
build:
	docker build -t $(IMAGE_NAME):$(TAG) .

build-gpu:
	docker build -f Dockerfile.gpu -t $(IMAGE_GPU):$(TAG_GPU) .

run-gpu-resnet:
	docker run --rm --gpus all $(IMAGE_GPU):$(TAG_GPU) --task resnet

run-bench-resnet:
	docker run --rm $(IMAGE_NAME):$(TAG) --task resnet

# Run all four CPU benchmarks in sequence (rebuilds image first; needs Docker)
smoke: build
	docker run --rm $(IMAGE_NAME):$(TAG) --task resnet
	docker run --rm $(IMAGE_NAME):$(TAG) --task bert
	docker run --rm $(IMAGE_NAME):$(TAG) --task yolo
	docker run --rm $(IMAGE_NAME):$(TAG) --task dlrm

# 4. Load image into Minikube (then set Job YAML to image: $(IMAGE_NAME):$(TAG) and imagePullPolicy: Never)
load:
	minikube image load $(IMAGE_NAME):$(TAG)

# 5. Apply default-scheduler Job (ResNet benchmark; see k8s/scheduling/)
run:
	kubectl apply -f k8s/scheduling/job-scheduler-default.yaml

# Secondary kube-schedulers: bin-pack (MostAllocated) + spread (LeastAllocated), one Deployment each.
install-secondary-scheduler:
	kubectl apply -f k8s/scheduling/secondary-scheduler-rbac.yaml
	kubectl apply -f k8s/scheduling/secondary-scheduler-binpack.yaml
	kubectl apply -f k8s/scheduling/secondary-scheduler-spread.yaml

uninstall-secondary-scheduler:
	kubectl delete deployment second-scheduler-binpack second-scheduler-spread -n kube-system --ignore-not-found=true
	kubectl delete configmap second-scheduler-binpack-config second-scheduler-spread-config -n kube-system --ignore-not-found=true
	kubectl delete clusterrolebinding second-scheduler-as-kube-scheduler --ignore-not-found=true
	kubectl delete serviceaccount second-scheduler -n kube-system --ignore-not-found=true

# Volcano (gang scheduling). Pin release in URL if your cluster version requires it.
install-volcano:
	kubectl apply -f https://raw.githubusercontent.com/volcano-sh/volcano/release-1.9/installer/volcano-development.yaml

# Delete workloads in ml-scheduling (batch/v1 Jobs + Volcano Jobs if installed)
clean-jobs:
	kubectl delete jobs -n ml-scheduling --all --ignore-not-found=true
	-kubectl delete jobs.batch.volcano.sh -n ml-scheduling --all --ignore-not-found=true

# Tear down the cluster
clean:
	$(MAKE) clean-jobs
	minikube delete
