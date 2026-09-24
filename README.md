# AI Incident Commander

[![CI](https://github.com/Sosa-IQ/ai-incident-commander/actions/workflows/ci.yml/badge.svg)](https://github.com/Sosa-IQ/ai-incident-commander/actions/workflows/ci.yml)

A read-only, evidence-based cloud incident investigation system built to learn and demonstrate **LangGraph, AI agents, Python, AWS Lambda, and Amazon EKS** in one coherent project.

![Dashboard architecture](https://img.shields.io/badge/LangGraph-6_agents-28d7c8) ![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab) ![AWS](https://img.shields.io/badge/AWS-Lambda_%2B_EKS-ff9900)

## What it does

Submit an incident with a service name, description, logs, and metrics. A LangGraph workflow runs six specialists:

1. **Triage agent** classifies impact.
2. **Metrics agent** extracts telemetry evidence.
3. **Logs agent** extracts event evidence.
4. **Root-cause agent** ranks a hypothesis.
5. **Runbook agent** proposes safe next steps.
6. **Incident commander** produces the final report.

The graph branches after triage: high/critical incidents inspect metrics first; lower-risk incidents inspect logs first. Every result carries evidence, confidence, an agent timeline, and `requires_human_approval=true`. The system has no workload-mutation permissions.

## Try it locally in two commands

```bash
cp .env.example .env
make setup && make local
```

Open <http://127.0.0.1:8080>. The default deterministic mode requires no API key and includes three demo incidents. To use actual LLM agents, set these in `.env`:

```dotenv
LLM_MODE=openai
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4o-mini
```

Then restart `make local`. API documentation is at <http://127.0.0.1:8080/docs>.

## AWS architecture

```text
CloudWatch alarms ─┐
Custom EventBridge ├─> Lambda ingest ─> SQS ─> EKS worker ─┐
                   │                                        ├─> LangGraph agents
Browser ── kubectl private tunnel ─────> EKS FastAPI ──────┘
                                                            ├─> DynamoDB current report
                                                            └─> S3 versioned archive
Container image: ECR     Pod identity: EKS IRSA     Failures: SQS DLQ
```

- **Lambda** is the burst-friendly ingestion and normalization boundary.
- **SQS** decouples alarms from investigations and retries failures through a DLQ.
- **EKS** hosts the API and long-running worker, making scaling and Kubernetes operations visible.
- **DynamoDB/S3** keep queryable reports and durable versioned evidence.
- **ECR** stores the immutable application image.
- **Terraform** creates the complete AWS environment.

See [Architecture](docs/ARCHITECTURE.md), [AWS deployment guide](docs/AWS_DEPLOYMENT.md), [ways to use it](docs/USE_CASES.md), and [security model](docs/SECURITY.md).

## Commands

| Command | Purpose |
|---|---|
| `make setup` | Install locked Python dependencies with uv |
| `make local` | Run the dashboard/API locally |
| `make check` | Lint, format-check, type-check, and test |
| `docker compose up --build` | Run the production container locally |
| `make deploy` | Create AWS resources, build/push the image, deploy to EKS |
| `make destroy` | Delete the Kubernetes service and Terraform resources |

## Project map

```text
src/incident_commander/   FastAPI, LangGraph workflow, storage, SQS worker
lambda_src/               Dependency-light Lambda ingestion handler
infra/                    Terraform for EKS, Lambda, SQS, DynamoDB, S3, ECR
k8s/                      Restricted Kubernetes workloads and private Service
scripts/                  One-command deploy/destroy and manifest rendering
tests/                    Unit, API, workflow, Lambda, worker, and asset tests
docs/PROJECT_IDEAS.md     All five original project ideas
```

## Safety and limitations

This is an educational incident-investigation system, not an autonomous remediation platform. Deterministic mode recognizes the included scenarios; OpenAI mode can generalize but may still be wrong. Treat all outputs as hypotheses, redact sensitive logs before model calls, add authentication before public production use, and keep human approval mandatory.

## License

MIT — see [LICENSE](LICENSE).
