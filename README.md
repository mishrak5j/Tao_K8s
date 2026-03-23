# Kubernetes Resource Management for ML Workloads

**Course:** CSC4311 - Cloud Computing (Spring 2026)  
**Author:** Kshitij Mishra

## 1. Project Motivation

This project evaluates how different Kubernetes scheduling strategies impact the performance of 5 distinct Machine Learning tasks. We analyze the trade-offs between resource utilization and model training throughput.

## 2. System Architecture

The system consists of:

- **Local Cluster:** Minikube (running on Docker driver).
- **Workloads:** 5 containerized Python ML tasks (Random Forest, CNN, etc.).
- **Schedulers:** Default K8s Scheduler, Resource Quotas, Priority Classes, and Node Affinity.

## 3. Prerequisites

- Compatible ARM64/x86 system
- Docker Desktop
- Minikube & Kubectl (`brew install minikube kubectl`)

## 4. How to Build and Run

### Step 1: Start the Cluster

```bash
minikube start --driver=docker --cpus=4 --memory=6144
```
