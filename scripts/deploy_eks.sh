#!/usr/bin/env bash
# First deploy from your laptop, after `terraform apply`.
# Builds the image, pushes it to ECR, installs External Secrets Operator, applies the manifests.
set -euo pipefail

TF_DIR="infra/terraform"
ESO_CHART_VERSION="${ESO_CHART_VERSION:-0.19.2}" # check: helm search repo external-secrets/external-secrets --versions | head

REGION="$(terraform -chdir="$TF_DIR" output -raw region)"
CLUSTER="$(terraform -chdir="$TF_DIR" output -raw cluster_name)"
REPO_URL="$(terraform -chdir="$TF_DIR" output -raw ecr_repository_url)"
REGISTRY="${REPO_URL%%/*}"
TAG="local-$(git rev-parse --short HEAD)-$(date +%s)"

echo "==> kubeconfig"
aws eks update-kubeconfig --region "$REGION" --name "$CLUSTER"

echo "==> build + push ${REPO_URL}:${TAG} (linux/amd64 to match the nodes)"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/amd64 -t "${REPO_URL}:${TAG}" --push .
DIGEST="$(aws ecr describe-images --region "$REGION" --repository-name "${REPO_URL##*/}" \
  --image-ids imageTag="$TAG" --query 'imageDetails[0].imageDigest' --output text)"
IMAGE="${REPO_URL}@${DIGEST}"
echo "    image: $IMAGE"

echo "==> External Secrets Operator ${ESO_CHART_VERSION}"
helm repo add external-secrets https://charts.external-secrets.io >/dev/null 2>&1 || true
helm repo update external-secrets >/dev/null
helm upgrade --install external-secrets external-secrets/external-secrets \
  --namespace external-secrets --create-namespace \
  --version "$ESO_CHART_VERSION" --set installCRDs=true --wait

echo "==> app manifests"
kubectl kustomize deploy/k8s \
  | sed -e "s#IMAGE_PLACEHOLDER#${IMAGE}#" -e "s#region: us-east-1#region: ${REGION}#" \
  | kubectl apply -f -

kubectl -n triagegpt wait --for=condition=Ready externalsecret/api-keys --timeout=120s
kubectl -n triagegpt rollout status deployment/triagegpt --timeout=300s

echo
echo "Deployed. Open it with:"
echo "  kubectl -n triagegpt port-forward svc/triagegpt 8501:80   # then http://localhost:8501"
