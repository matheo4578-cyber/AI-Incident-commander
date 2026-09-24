#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
export AWS_REGION="${AWS_REGION:-${TF_VAR_aws_region:-us-east-1}}"
export TF_VAR_aws_region="${TF_VAR_aws_region:-$AWS_REGION}"
export TF_VAR_project_name="${TF_VAR_project_name:-ai-incident-commander}"
for cmd in aws kubectl terraform uv; do command -v "$cmd" >/dev/null || { echo "Missing required command: $cmd" >&2; exit 1; }; done
read -r -p "Destroy all AI Incident Commander AWS resources? Type destroy: " confirmation
[[ "$confirmation" == "destroy" ]] || { echo "Cancelled"; exit 1; }
# Delete application workloads before Terraform destroys the cluster.
CLUSTER_NAME=$(terraform -chdir=infra output -raw cluster_name 2>/dev/null || true)
if [[ -n "$CLUSTER_NAME" ]]; then
  aws eks update-kubeconfig --region "$AWS_REGION" --name "$CLUSTER_NAME" >/dev/null 2>&1 || true
  kubectl delete namespace incident-commander --ignore-not-found --timeout=3m || true
fi
BUCKET=$(terraform -chdir=infra output -raw reports_bucket 2>/dev/null || true)
if [[ -n "$BUCKET" ]]; then
  uv run python scripts/empty_versioned_bucket.py "$BUCKET"
fi
terraform -chdir=infra destroy
