output "cluster_name" { value = aws_eks_cluster.main.name }
output "ecr_repository_url" { value = aws_ecr_repository.app.repository_url }
output "incident_queue_url" { value = aws_sqs_queue.incidents.url }
output "reports_table" { value = aws_dynamodb_table.reports.name }
output "reports_bucket" { value = aws_s3_bucket.reports.id }
output "api_role_arn" { value = aws_iam_role.api.arn }
output "worker_role_arn" { value = aws_iam_role.worker.arn }
output "lambda_function_name" { value = aws_lambda_function.ingest.function_name }
