variable "aws_region" {
  description = "AWS region for the offsite backup bucket."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Globally unique name for the private backup bucket."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid S3 bucket name between 3 and 63 characters."
  }
}

variable "backup_user_name" {
  description = "IAM user used only by the homelab upload jobs."
  type        = string
  default     = "aws-homelab-dr-uploader"

  validation {
    condition     = can(regex("^[A-Za-z0-9+=,.@_-]{1,64}$", var.backup_user_name))
    error_message = "backup_user_name must be a valid IAM user name."
  }
}
