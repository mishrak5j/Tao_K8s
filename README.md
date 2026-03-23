# Kubernetes Resource Management for ML Workloads
[cite_start]**Course:** CSC4311 - Cloud Computing (Spring 2026) [cite: 25]
[cite_start]**Instructor:** Dr. Bingyi Xie [cite: 26]
**Author:** Kshitij Mishra

## 1. Project Motivation
[cite_start]This project evaluates how different Kubernetes scheduling strategies impact the performance of 5 distinct Machine Learning tasks[cite: 14]. [cite_start]We analyze the trade-offs between resource utilization and model training throughput[cite: 67].

## 2. System Architecture
The system consists of:
- [cite_start]**Local Cluster:** Minikube (running on Docker driver)[cite: 63].
- **Workloads:** 5 containerized Python ML tasks (Random Forest, CNN, etc.).
- **Schedulers:** Default K8s Scheduler, Resource Quotas, Priority Classes, and Node Affinity.

## 3. Prerequisites
- compatible ARM64/x86 system
- Docker Desktop
- Minikube & Kubectl (`brew install minikube kubectl`)

## [cite_start]4. How to Build and Run [cite: 11, 82]

### Step 1: Start the Cluster
```bash
minikube start --driver=docker --cpus=4 --memory=6144