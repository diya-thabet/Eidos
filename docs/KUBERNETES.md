# Kubernetes Deployment Guide

## Overview

Eidos can be deployed locally using **kind** (Kubernetes IN Docker) or
**minikube** for testing and development.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Docker | 20+ | https://docs.docker.com/get-docker/ |
| kubectl | 1.28+ | https://kubernetes.io/docs/tasks/tools/ |
| kind | 0.20+ | `go install sigs.k8s.io/kind@latest` |
| minikube | 1.32+ | https://minikube.sigs.k8s.io/docs/start/ |

## Quick Start

### Using kind

```bash
chmod +x k8s/deploy-local.sh
./k8s/deploy-local.sh kind
```

### Using minikube

```bash
chmod +x k8s/deploy-local.sh
./k8s/deploy-local.sh minikube
```

## What Gets Deployed

```
eidos namespace
  |
  +-- postgres (Deployment + Service + PVC)
  |     PostgreSQL 16 Alpine
  |     Port: 5432
  |     Storage: 2Gi PVC
  |
  +-- redis (Deployment + Service)
  |     Redis 7 Alpine
  |     Port: 6379
  |
  +-- qdrant (Deployment + Service + PVC)
  |     Qdrant v1.9.7
  |     Ports: 6333 (HTTP), 6334 (gRPC)
  |     Storage: 2Gi PVC
  |
  +-- eidos-api (Deployment + Service + NodePort)
        Custom Python image
        Port: 8000 (internal), 30080 (NodePort)
        Storage: 5Gi PVC for cloned repos
```

## Manifest Files

| File | Contents |
|------|----------|
| `k8s/namespace.yaml` | `eidos` namespace |
| `k8s/configmap.yaml` | Non-secret configuration (DB URLs, paths) |
| `k8s/secrets.yaml` | Sensitive values (API keys, passwords) |
| `k8s/infrastructure.yaml` | PostgreSQL, Redis, Qdrant deployments + services |
| `k8s/api.yaml` | Eidos API deployment + ClusterIP + NodePort services |
| `k8s/deploy-local.sh` | Automated deployment script |

## Manual Deployment

```bash
# 1. Create cluster
kind create cluster --name eidos-dev

# 2. Build and load image
docker build -t eidos-api:latest ./backend
kind load docker-image eidos-api:latest --name eidos-dev

# 3. Apply manifests (order matters)
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/infrastructure.yaml
kubectl apply -f k8s/api.yaml

# 4. Wait and verify
kubectl -n eidos get pods -w
```

## Accessing the API

### kind
The NodePort maps to `localhost:30080`:
```bash
curl http://localhost:30080/health
```

### minikube
```bash
minikube -p eidos-dev service eidos-api-nodeport -n eidos --url
```

## Health Checks

All deployments include readiness probes:

| Service | Probe | Interval |
|---------|-------|----------|
| PostgreSQL | `pg_isready -U eidos` | 10s |
| Redis | `redis-cli ping` | 5s |
| Qdrant | `GET /healthz` | 10s |
| Eidos API | `GET /health` | 10s |

## Resource Limits

| Service | Request (CPU/Mem) | Limit (CPU/Mem) |
|---------|-------------------|-----------------|
| PostgreSQL | 250m / 256Mi | 500m / 512Mi |
| Redis | 100m / 64Mi | 200m / 128Mi |
| Qdrant | 250m / 256Mi | 500m / 512Mi |
| Eidos API | 250m / 256Mi | 1000m / 1Gi |

## Teardown

```bash
# kind
kind delete cluster --name eidos-dev

# minikube
minikube delete -p eidos-dev
```

## Troubleshooting

### Pods stuck in Pending
```bash
kubectl -n eidos describe pod <pod-name>
# Check for PVC binding issues or resource constraints
```

### API can't connect to Postgres
```bash
kubectl -n eidos logs deployment/eidos-api
# The init container waits for postgres; check postgres pod status
```

### Image not found
```bash
# Make sure image is loaded into the cluster
kind load docker-image eidos-api:latest --name eidos-dev
# Or for minikube:
minikube -p eidos-dev image load eidos-api:latest
```
