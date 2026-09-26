output "backup_bucket_name" {
  description = "Name of the private S3 bucket used for backup sets."
  value       = aws_s3_bucket.backups.bucket
}

output "backup_bucket_arn" {
  description = "ARN of the private S3 bucket used for backup sets."
  value       = aws_s3_bucket.backups.arn
}

output "backup_uploader_user_name" {
  description = "IAM user that will receive an access key outside Terraform."
  value       = aws_iam_user.backup_uploader.name
}
