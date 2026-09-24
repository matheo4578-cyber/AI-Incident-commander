data "aws_availability_zones" "available" { state = "available" }
data "aws_caller_identity" "current" {}

data "archive_file" "lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda_src/handler.py"
  output_path = "${path.module}/lambda.zip"
}

locals {
  tags = {
    Project   = var.project_name
    ManagedBy = "Terraform"
  }
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "main" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.project_name}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project_name}-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  availability_zone       = local.azs[count.index]
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  map_public_ip_on_launch = true
  tags = {
    Name                                            = "${var.project_name}-public-${count.index + 1}"
    "kubernetes.io/role/elb"                        = "1"
    "kubernetes.io/cluster/${var.project_name}-eks" = "shared"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${var.project_name}-public" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_iam_role" "eks_cluster" {
  name = "${var.project_name}-eks-cluster"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "eks.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy_attachment" "eks_cluster" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-eks"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.kubernetes_version
  vpc_config {
    subnet_ids              = aws_subnet.public[*].id
    endpoint_private_access = true
    endpoint_public_access  = true
    public_access_cidrs     = var.cluster_public_access_cidrs
  }
  access_config {
    authentication_mode                         = "API_AND_CONFIG_MAP"
    bootstrap_cluster_creator_admin_permissions = true
  }
  depends_on = [aws_iam_role_policy_attachment.eks_cluster]
}

resource "aws_iam_role" "eks_nodes" {
  name = "${var.project_name}-eks-nodes"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}
resource "aws_iam_role_policy_attachment" "node_ecr" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPullOnly"
}
resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "general"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = aws_subnet.public[*].id
  instance_types  = [var.node_instance_type]
  capacity_type   = "ON_DEMAND"
  scaling_config {
    desired_size = 1
    min_size     = 1
    max_size     = 2
  }
  update_config { max_unavailable = 1 }
  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_ecr,
    aws_iam_role_policy_attachment.node_cni,
  ]
}

resource "aws_ecr_repository" "app" {
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = true
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "incidents" {
  name                       = "${var.project_name}-incidents"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = 3 })
}
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url            = aws_sqs_queue.dlq.id
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.incidents.arn] })
}

resource "aws_dynamodb_table" "reports" {
  name         = "${var.project_name}-reports"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "incident_id"
  attribute {
    name = "incident_id"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
}

resource "aws_s3_bucket" "reports" {
  bucket        = "${var.project_name}-reports-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "reports" {
  bucket                  = aws_s3_bucket.reports.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "reports" {
  bucket = aws_s3_bucket.reports.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy" "lambda" {
  name = "ingest"
  role = aws_iam_role.lambda.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.incidents.arn },
    { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], Resource = "arn:aws:logs:*:*:*" }
  ] })
}
resource "aws_lambda_function" "ingest" {
  function_name    = "${var.project_name}-ingest"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  role             = aws_iam_role.lambda.arn
  handler          = "handler.handler"
  runtime          = "python3.12"
  timeout          = 10
  memory_size      = 128
  environment { variables = { INCIDENT_QUEUE_URL = aws_sqs_queue.incidents.url } }
}

resource "aws_cloudwatch_event_rule" "incidents" {
  name          = "${var.project_name}-alarms"
  event_pattern = jsonencode({ source = ["aws.cloudwatch"], "detail-type" = ["CloudWatch Alarm State Change"], detail = { state = { value = ["ALARM"] } } })
}
resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.incidents.name
  arn  = aws_lambda_function.ingest.arn
}
resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.incidents.arn
}

resource "aws_cloudwatch_event_rule" "custom_incidents" {
  name          = "${var.project_name}-custom-incidents"
  event_pattern = jsonencode({ source = ["incident.commander"], "detail-type" = ["Incident Report"] })
}
resource "aws_cloudwatch_event_target" "custom_lambda" {
  rule = aws_cloudwatch_event_rule.custom_incidents.name
  arn  = aws_lambda_function.ingest.arn
}
resource "aws_lambda_permission" "custom_eventbridge" {
  statement_id  = "AllowCustomEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingest.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.custom_incidents.arn
}

# Separate IRSA roles keep the API and queue worker at least privilege.
data "tls_certificate" "eks" { url = aws_eks_cluster.main.identity[0].oidc[0].issuer }
resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
}

resource "aws_iam_role" "api" {
  name = "${var.project_name}-api"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = aws_iam_openid_connect_provider.eks.arn },
    Condition = { StringEquals = {
      "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud" = "sts.amazonaws.com",
      "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub" = "system:serviceaccount:incident-commander:incident-commander-api"
    } }
  }] })
}
resource "aws_iam_role_policy" "api" {
  name = "reports"
  role = aws_iam_role.api.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:GetItem"], Resource = aws_dynamodb_table.reports.arn },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.reports.arn}/reports/*" }
  ] })
}

resource "aws_iam_role" "worker" {
  name = "${var.project_name}-worker"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = aws_iam_openid_connect_provider.eks.arn },
    Condition = { StringEquals = {
      "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:aud" = "sts.amazonaws.com",
      "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub" = "system:serviceaccount:incident-commander:incident-commander-worker"
    } }
  }] })
}
resource "aws_iam_role_policy" "worker" {
  name = "queue-and-reports"
  role = aws_iam_role.worker.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"], Resource = aws_sqs_queue.incidents.arn },
    { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:GetItem"], Resource = aws_dynamodb_table.reports.arn },
    { Effect = "Allow", Action = ["s3:PutObject"], Resource = "${aws_s3_bucket.reports.arn}/reports/*" }
  ] })
}
