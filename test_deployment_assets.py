import re
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_container_runs_as_non_root_and_has_healthcheck() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "USER 10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile


def test_kubernetes_workloads_enforce_basic_security() -> None:
    manifests = "\n".join(path.read_text() for path in (ROOT / "k8s").glob("*.yaml"))

    assert "runAsNonRoot: true" in manifests
    assert "readOnlyRootFilesystem: true" in manifests
    assert "allowPrivilegeEscalation: false" in manifests
    assert "kind: Deployment" in manifests
    assert "type: LoadBalancer" not in manifests
    assert "name: incident-commander-api" in manifests
    assert "name: incident-commander-worker" in manifests


def test_terraform_defines_required_aws_services() -> None:
    terraform = "\n".join(path.read_text() for path in (ROOT / "infra").glob("*.tf"))

    for resource in (
        'resource "aws_lambda_function"',
        'resource "aws_eks_cluster"',
        'resource "aws_eks_node_group"',
        'resource "aws_sqs_queue"',
        'resource "aws_dynamodb_table"',
        'resource "aws_s3_bucket"',
        'resource "aws_ecr_repository"',
    ):
        assert resource in terraform
    assert "public_access_cidrs" in terraform
    assert 'resource "aws_iam_role" "api"' in terraform
    assert 'resource "aws_iam_role" "worker"' in terraform
    assert re.search(r"force_delete\s*=\s*true", terraform)
    assert 'endswith(cidr, "/32")' in terraform


def test_environment_template_does_not_contain_live_secrets() -> None:
    template = (ROOT / ".env.example").read_text()

    assert "OPENAI_API_KEY=" in template
    assert "OPENAI_API_KEY=sk-" not in template
    assert "AWS_SECRET_ACCESS_KEY=" not in template


def test_ci_runs_quality_and_container_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "uv run pytest" in workflow
    assert "uv run ruff check" in workflow
    assert "uv run mypy" in workflow
    assert "docker build" in workflow
    assert "terraform validate" in workflow


def test_deploy_reuses_existing_immutable_image_and_does_not_claim_public_url() -> None:
    script = (ROOT / "scripts" / "deploy_aws.sh").read_text()

    assert "describe-images" in script
    assert "port-forward service/api" in script
    assert "Deployment complete: http://" not in script


def test_custom_eventbridge_example_exists() -> None:
    assert (ROOT / "examples" / "custom-eventbridge-entry.json").is_file()


def test_destroy_empties_versioned_bucket_before_terraform() -> None:
    script = (ROOT / "scripts" / "destroy_aws.sh").read_text()

    assert "empty_versioned_bucket.py" in script
    assert (ROOT / "scripts" / "empty_versioned_bucket.py").is_file()
