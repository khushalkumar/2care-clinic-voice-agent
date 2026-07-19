output "api_base_url" {
  value = "https://${aws_cloudfront_distribution.app.domain_name}"
}

output "application_secret_arn" {
  value       = aws_secretsmanager_secret.application.arn
  description = "Populate required JSON keys out of band before starting ECS."
}

output "database_master_secret_arn" {
  value     = aws_db_instance.postgres.master_user_secret[0].secret_arn
  sensitive = true
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "jobs_queue_url" {
  value = aws_sqs_queue.jobs.url
}
