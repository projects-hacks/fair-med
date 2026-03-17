# FairMed — Deployment Guide

## Infrastructure

| Component | Detail |
|-----------|--------|
| Cloud | Linode (Akamai) LKE |
| Cluster | `fairmed` (ID: 580941) |
| Region | US, Fremont, CA |
| Nodes | 2 × Linode 4 GB |
| K8s Version | 1.35 |
| Container Registry | ghcr.io/rajeev-chaurasia/fair-med |
| External IP | `23.239.6.35` |
| API Base URL | `http://23.239.6.35` |

## Prerequisites

- Docker Desktop running
- `kubectl` installed
- `gh` CLI authenticated (`gh auth status`)
- Kubeconfig at `k8s/fairmed-kubeconfig.yaml`

## Push a Backend Update

```bash
# 1. Build for amd64 and push to GHCR (one command)
docker buildx build --platform linux/amd64 \
  -t ghcr.io/rajeev-chaurasia/fair-med:latest \
  --push .

# 2. Restart pods to pull new image
export KUBECONFIG=k8s/fairmed-kubeconfig.yaml
kubectl -n fairmed rollout restart deployment fairmed-api

# 3. Watch rollout
kubectl -n fairmed rollout status deployment fairmed-api

# 4. Verify
curl http://23.239.6.35/api/health
```

That's it. Three commands to deploy any change.

## First-Time Setup (already done)

For reference, here's what was set up initially:

```bash
# Set kubeconfig
export KUBECONFIG=k8s/fairmed-kubeconfig.yaml

# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create GHCR pull secret (so K8s can pull private images)
GH_TOKEN=$(gh auth token)
kubectl create secret docker-registry ghcr-pull-secret \
  --namespace=fairmed \
  --docker-server=ghcr.io \
  --docker-username=rajeev-chaurasia \
  --docker-password="$GH_TOKEN" \
  --docker-email=rajeev-chaurasia@users.noreply.github.com

# Apply secrets (NVIDIA + Supabase keys)
kubectl apply -f k8s/secret.yaml

# Deploy app + service
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

## Useful Commands

```bash
export KUBECONFIG=k8s/fairmed-kubeconfig.yaml

# Check pod status
kubectl -n fairmed get pods

# View logs (live)
kubectl -n fairmed logs -f deployment/fairmed-api

# View logs for a specific pod
kubectl -n fairmed logs <pod-name>

# Shell into a pod
kubectl -n fairmed exec -it <pod-name> -- /bin/bash

# Check resource usage
kubectl -n fairmed top pods

# Scale replicas
kubectl -n fairmed scale deployment fairmed-api --replicas=3

# Check external IP
kubectl -n fairmed get svc fairmed-api
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Liveness probe |
| POST | `/api/analyze` | Start bill analysis → `{ "bill_text": "..." }` |
| GET | `/api/analyze/{job_id}` | Poll analysis results |
| POST | `/api/letter/{job_id}` | Trigger letter generation |
| GET | `/api/letter/{job_id}` | Poll/download letter |

## Updating Secrets

If API keys change:

```bash
# Edit the secret file
# k8s/secret.yaml  (gitignored — safe)

# Apply
kubectl apply -f k8s/secret.yaml

# Restart pods to pick up new env vars
kubectl -n fairmed rollout restart deployment fairmed-api
```

## Files

| File | Purpose |
|------|---------|
| `server.py` | FastAPI backend |
| `Dockerfile` | Container image definition |
| `.dockerignore` | Keeps image small |
| `k8s/namespace.yaml` | Namespace |
| `k8s/secret.yaml` | API keys (gitignored) |
| `k8s/deployment.yaml` | 2 replicas, probes, resources |
| `k8s/service.yaml` | LoadBalancer → public IP |
| `k8s/fairmed-kubeconfig.yaml` | Cluster auth (gitignored) |
