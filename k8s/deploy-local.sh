#!/bin/bash
# ============================================================================
# Eidos - Local Kubernetes Deployment Script
#
# Prerequisites:
#   - Docker installed and running
#   - kind (https://kind.sigs.k8s.io/) OR minikube installed
#   - kubectl installed
#
# Usage:
#   ./deploy-local.sh kind    # Deploy using kind
#   ./deploy-local.sh minikube # Deploy using minikube
# ============================================================================

set -euo pipefail

TOOL="${1:-kind}"
CLUSTER_NAME="eidos-dev"

echo "=== Eidos Local K8s Deployment ==="
echo "Tool: $TOOL"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Create cluster
# ---------------------------------------------------------------------------
if [ "$TOOL" = "kind" ]; then
    if ! kind get clusters 2>/dev/null | grep -q "$CLUSTER_NAME"; then
        echo "[1/5] Creating kind cluster '$CLUSTER_NAME'..."
        kind create cluster --name "$CLUSTER_NAME" --config - <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 30080
        protocol: TCP
EOF
    else
        echo "[1/5] Kind cluster '$CLUSTER_NAME' already exists."
    fi
elif [ "$TOOL" = "minikube" ]; then
    if ! minikube status -p "$CLUSTER_NAME" &>/dev/null; then
        echo "[1/5] Starting minikube profile '$CLUSTER_NAME'..."
        minikube start -p "$CLUSTER_NAME" --memory=4096 --cpus=2
    else
        echo "[1/5] Minikube profile '$CLUSTER_NAME' already running."
    fi
fi

# ---------------------------------------------------------------------------
# Step 2: Build Docker image
# ---------------------------------------------------------------------------
echo "[2/5] Building eidos-api Docker image..."
docker build -t eidos-api:latest ./backend

if [ "$TOOL" = "kind" ]; then
    echo "  Loading image into kind cluster..."
    kind load docker-image eidos-api:latest --name "$CLUSTER_NAME"
elif [ "$TOOL" = "minikube" ]; then
    echo "  Loading image into minikube..."
    minikube -p "$CLUSTER_NAME" image load eidos-api:latest
fi

# ---------------------------------------------------------------------------
# Step 3: Apply Kubernetes manifests
# ---------------------------------------------------------------------------
echo "[3/5] Applying Kubernetes manifests..."
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/infrastructure.yaml
kubectl apply -f k8s/api.yaml

# ---------------------------------------------------------------------------
# Step 4: Wait for pods
# ---------------------------------------------------------------------------
echo "[4/5] Waiting for pods to be ready..."
kubectl -n eidos wait --for=condition=ready pod -l app=postgres --timeout=120s
kubectl -n eidos wait --for=condition=ready pod -l app=redis --timeout=60s
kubectl -n eidos wait --for=condition=ready pod -l app=qdrant --timeout=60s
kubectl -n eidos wait --for=condition=ready pod -l app=eidos-api --timeout=120s

# ---------------------------------------------------------------------------
# Step 5: Verify
# ---------------------------------------------------------------------------
echo "[5/5] Verifying deployment..."
echo ""
kubectl -n eidos get pods
echo ""

if [ "$TOOL" = "kind" ]; then
    API_URL="http://localhost:30080"
elif [ "$TOOL" = "minikube" ]; then
    API_URL="$(minikube -p "$CLUSTER_NAME" service eidos-api-nodeport -n eidos --url)"
fi

echo "Checking health endpoint..."
if curl -sf "${API_URL}/health" > /dev/null 2>&1; then
    echo "  API is healthy at ${API_URL}"
else
    echo "  API not yet responding at ${API_URL} (may need a few more seconds)"
fi

echo ""
echo "=== Deployment complete ==="
echo "API URL: ${API_URL}"
echo ""
echo "Try:"
echo "  curl ${API_URL}/health"
echo "  curl -X POST ${API_URL}/repos -H 'Content-Type: application/json' -d '{\"name\":\"test\",\"url\":\"https://github.com/dotnet/samples\"}'"
echo ""
echo "To tear down:"
if [ "$TOOL" = "kind" ]; then
    echo "  kind delete cluster --name $CLUSTER_NAME"
else
    echo "  minikube delete -p $CLUSTER_NAME"
fi
