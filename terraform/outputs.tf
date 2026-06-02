output "raw_billing_bucket" {
  description = "S3 bucket for raw billing CSV uploads."
  value       = aws_s3_bucket.raw_billing.bucket
}

output "curated_billing_bucket" {
  description = "S3 bucket for processed analytics files."
  value       = aws_s3_bucket.curated_billing.bucket
}

output "cost_alerts_topic_arn" {
  description = "SNS topic for cost alerts."
  value       = aws_sns_topic.cost_alerts.arn
}

output "etl_role_arn" {
  description = "IAM role ARN for a Lambda or scheduled ETL job."
  value       = aws_iam_role.etl_role.arn
}
