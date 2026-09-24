# Detailed AWS deployment guide

The repository is complete through source, tests, container, Lambda, EKS manifests, infrastructure, and automation. You provide credentials and choose the environment; the script performs the build and deployment.

## 0. Cost warning

EKS has a continuously billed control plane and at least one EC2 worker in this configuration. Storage, logs, and model usage may also cost money. Check the current AWS Pricing Calculator for your region. Run `make destroy` when you finish; stopping your laptop does not stop AWS charges.

## 1. Accounts and local tools

You need:

- An AWS account and an IAM principal allowed to create VPC, IAM, EKS, EC2, ECR, Lambda, EventBridge, SQS, DynamoDB, and S3 resources.
- AWS CLI, Docker, kubectl, Terraform, Git, Python 3.11+, and uv.
- An OpenAI API key only if you choose `LLM_MODE=openai`.

On macOS with Homebrew:

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform awscli kubectl docker colima uv
colima start --cpu 4 --memory 8
```

Docker Desktop can replace Docker + Colima.

## 2. Configure AWS credentials

Recommended interactive setup:

```bash
aws configure sso
aws sso login --profile YOUR_PROFILE
```

Traditional access keys also work with `aws configure --profile YOUR_PROFILE`. Do not put AWS access keys in `.env` or Git. Verify the credential chain:

```bash
AWS_PROFILE=YOUR_PROFILE aws sts get-caller-identity
```

## 3. Configure environment variables

```bash
cd ~/Projects/ai-incident-commander
cp .env.example .env
```

Edit `.env`:

```dotenv
AWS_PROFILE=YOUR_PROFILE
AWS_REGION=us-east-1
TF_VAR_aws_region=us-east-1
TF_VAR_project_name=ai-incident-commander
# Replace this example with your current public IPv4 address plus /32.
# `curl -s https://checkip.amazonaws.com` shows the address.
TF_VAR_cluster_public_access_cidrs='["203.0.113.10/32"]'
TF_VAR_kubernetes_version=1.34

# Start without model spend:
LLM_MODE=deterministic
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

For LLM-backed triage, root-cause, and commander agents:

```dotenv
LLM_MODE=openai
OPENAI_API_KEY=your-openai-key
OPENAI_MODEL=a-structured-output-capable-model-you-can-access
```

If the default Kubernetes version is unavailable in your region, list currently supported versions in the AWS console or CLI and change `TF_VAR_kubernetes_version`.

## 4. Verify before deploying

```bash
make setup
make check
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
aws sts get-caller-identity
```

## 5. Deploy end to end

```bash
make deploy
```

The script:

1. loads `.env` and validates prerequisites;
2. creates the VPC, two public subnets, CIDR-restricted EKS cluster/node group, ECR, Lambda, EventBridge rules, SQS/DLQ, DynamoDB, S3, and separate least-privilege API/worker roles;
3. builds and pushes an immutable Git-SHA image, or safely reuses it when that exact image already exists;
4. configures kubectl;
5. creates the OpenAI Kubernetes secret without adding it to Terraform state;
6. deploys the API and worker and waits for both rollouts;
7. prints the secure `kubectl port-forward` command and Lambda function name.

EKS creation commonly takes several minutes. The API is a private `ClusterIP` Service by default; no anonymous internet endpoint is created.

## 6. Verify the deployment

```bash
kubectl -n incident-commander get pods,service
kubectl -n incident-commander logs deployment/api --tail=50
kubectl -n incident-commander logs deployment/worker --tail=50
kubectl -n incident-commander port-forward service/api 8080:80
```

Leave the port-forward running, open <http://127.0.0.1:8080>, and submit a sample. In another terminal, verify health:

```bash
URL="http://127.0.0.1:8080"
curl -fsS "$URL/api/health"
```

Expected response:

```json
{"status":"ok","service":"incident-commander"}
```

## 7. Exercise Lambda → SQS → EKS

### Direct Lambda test

```bash
FUNCTION=$(terraform -chdir=infra output -raw lambda_function_name)
aws lambda invoke   --function-name "$FUNCTION"   --cli-binary-format raw-in-base64-out   --payload fileb://examples/cloudwatch-alarm.json   /tmp/incident-response.json
python3 -m json.tool /tmp/incident-response.json
```

Copy the returned `incident_id`, then retrieve it from the EKS API:

```bash
curl -fsS "$URL/api/incidents/INCIDENT_ID" | python3 -m json.tool
```

### Custom EventBridge event from a home server or another application

```bash
aws events put-events --entries file://examples/custom-eventbridge-entry.json
```

The sender only needs permission for `events:PutEvents` on the chosen event bus. Do not include credentials or sensitive log lines in event details.

## 8. Operate and troubleshoot

```bash
# Queue depth and DLQ
aws sqs get-queue-attributes   --queue-url "$(terraform -chdir=infra output -raw incident_queue_url)"   --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible

# Restart after changing environment/model settings
kubectl -n incident-commander rollout restart deployment/api deployment/worker

# Inspect AWS reports
aws dynamodb scan --table-name "$(terraform -chdir=infra output -raw reports_table)" --max-items 5
aws s3 ls "s3://$(terraform -chdir=infra output -raw reports_bucket)/reports/"
```

If pods cannot start, use `kubectl describe pod`. If they cannot access AWS services, verify the service-account role annotation and IRSA trust subject. If EKS rejects the Kubernetes version, change the environment value and rerun deployment.

## 9. Destroy and verify cleanup

```bash
make destroy
```

Type `destroy` at the first prompt. This explicitly authorizes permanent deletion of all report object versions/delete markers and ECR images. The script empties the versioned S3 bucket, removes the Kubernetes namespace, and then asks you to review and approve Terraform's destroy plan. Export any evidence you need before confirming.

Then verify:

```bash
terraform -chdir=infra show
aws eks describe-cluster --name ai-incident-commander-eks 2>&1 | grep -i ResourceNotFound
```

If cleanup is interrupted, rerun `make destroy`; the version-aware cleanup script and ECR deletion are idempotent. The typed confirmation is the destructive safety boundary.
