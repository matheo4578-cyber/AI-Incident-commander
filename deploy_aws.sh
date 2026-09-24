#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
for cmd in aws docker kubectl terraform python3 git; do command -v "$cmd" >/dev/null || { echo "Missing required command: $cmd" >&2; exit 1; }; done
export AWS_REGION="${AWS_REGION:-${TF_VAR_aws_region:-us-east-1}}"
export TF_VAR_aws_region="${TF_VAR_aws_region:-$AWS_REGION}"
export TF_VAR_project_name="${TF_VAR_project_name:-ai-incident-commander}"
: "${TF_VAR_cluster_public_access_cidrs:?Set TF_VAR_cluster_public_access_cidrs to a restricted JSON CIDR list, for example [\"203.0.113.10/32\"]}"
export LLM_MODE="${LLM_MODE:-deterministic}"
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}"
if [[ "$LLM_MODE" == "openai" && -z "${OPENAI_API_KEY:-}" ]]; then echo "OPENAI_API_KEY is required for LLM_MODE=openai" >&2; exit 1; fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Refusing to deploy a dirty tracked worktree; commit or restore changes first." >&2
  exit 1
fi
aws sts get-caller-identity >/dev/null
terraform -chdir=infra init
terraform -chdir=infra apply -auto-approve
CLUSTER_NAME=$(terraform -chdir=infra output -raw cluster_name)
ECR_URL=$(terraform -chdir=infra output -raw ecr_repository_url)
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_TAG=$(git rev-parse --short=12 HEAD)
IMAGE_URI="$ECR_URL:$IMAGE_TAG"
if aws ecr describe-images --repository-name "$TF_VAR_project_name" --image-ids imageTag="$IMAGE_TAG" >/dev/null 2>&1; then
  echo "Reusing existing immutable image: $IMAGE_URI"
else
  aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
  docker build --platform linux/amd64 -t "$IMAGE_URI" .
  docker push "$IMAGE_URI"
fi
aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME"
export IMAGE_URI
export API_ROLE_ARN
API_ROLE_ARN=$(terraform -chdir=infra output -raw api_role_arn)
export WORKER_ROLE_ARN
WORKER_ROLE_ARN=$(terraform -chdir=infra output -raw worker_role_arn)
export INCIDENT_QUEUE_URL
INCIDENT_QUEUE_URL=$(terraform -chdir=infra output -raw incident_queue_url)
export REPORTS_TABLE
REPORTS_TABLE=$(terraform -chdir=infra output -raw reports_table)
export REPORTS_BUCKET
REPORTS_BUCKET=$(terraform -chdir=infra output -raw reports_bucket)
kubectl apply -f <(printf '%s\n' 'apiVersion: v1' 'kind: Namespace' 'metadata:' '  name: incident-commander')
kubectl -n incident-commander create secret generic incident-commander-secrets --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" --dry-run=client -o yaml | kubectl apply -f -
python3 scripts/render_k8s.py | kubectl apply -f -
kubectl -n incident-commander rollout status deployment/api --timeout=5m
kubectl -n incident-commander rollout status deployment/worker --timeout=5m
echo "Deployment complete. The API remains private inside EKS."
echo "Connect securely: kubectl -n incident-commander port-forward service/api 8080:80"
echo "Then open: http://127.0.0.1:8080"
echo "Lambda ingestion: $(terraform -chdir=infra output -raw lambda_function_name)"
