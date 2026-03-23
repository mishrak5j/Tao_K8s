# Variables
IMAGE_NAME=ml-task-rf
TAG=latest
CPUS=4
MEM=6144

.PHONY: setup build load run lint clean

# 1. Setup the environment (Day 1 task)
setup:
	minikube start --driver=docker --cpus=$(CPUS) --memory=$(MEM)
	minikube addons enable metrics-server

# 2. Linting (Ensures code quality)
lint:
	pip install flake8
	flake8 src/*.py

# 3. Build the Docker image
build:
	docker build -t $(IMAGE_NAME):$(TAG) .

# 4. Load image into Minikube (Crucial step)
load:
	minikube image load $(IMAGE_NAME):$(TAG)

# 5. Run the K8s Job
run:
	kubectl apply -f k8s/ml-job.yaml

# 6. Clean up
clean:
	kubectl delete -f k8s/ml-job.yaml
	minikube delete