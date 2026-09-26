resource "aws_s3_bucket" "backups" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket = aws_s3_bucket.backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 lifecycle rules expire by object age. They provide a bounded, low-cost
# retention window without granting DeleteObject to any home VM.
resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  dynamic "rule" {
    for_each = toset(["nextcloud/", "npm/", "pihole/", "plex/biweekly/"])
    content {
      id     = "critical-${replace(trimsuffix(rule.value, "/"), "/", "-")}-91-days"
      status = "Enabled"

      filter {
        prefix = rule.value
      }

      expiration {
        days = 91
      }
    }
  }

  rule {
    id     = "plex-monthly-183-days"
    status = "Enabled"

    filter {
      prefix = "plex/monthly/"
    }

    expiration {
      days = 183
    }
  }
}

data "aws_iam_policy_document" "deny_insecure_transport" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.backups.arn,
      "${aws_s3_bucket.backups.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "backups" {
  bucket = aws_s3_bucket.backups.id
  policy = data.aws_iam_policy_document.deny_insecure_transport.json
}

resource "aws_iam_user" "backup_uploader" {
  name = var.backup_user_name
}

data "aws_iam_policy_document" "backup_uploader" {
  statement {
    sid = "ReadBucketLocation"
    actions = [
      "s3:GetBucketLocation",
    ]
    resources = [aws_s3_bucket.backups.arn]
  }

  statement {
    sid = "ListBackupPrefixes"
    actions = [
      "s3:ListBucket",
    ]
    resources = [aws_s3_bucket.backups.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values = [
        "nextcloud/*",
        "npm/*",
        "pihole/*",
        "plex/*",
      ]
    }
  }

  statement {
    sid = "UploadAndVerifyBackupObjects"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = [
      "${aws_s3_bucket.backups.arn}/nextcloud/*",
      "${aws_s3_bucket.backups.arn}/npm/*",
      "${aws_s3_bucket.backups.arn}/pihole/*",
      "${aws_s3_bucket.backups.arn}/plex/*",
    ]
  }
}

resource "aws_iam_user_policy" "backup_uploader" {
  user   = aws_iam_user.backup_uploader.name
  policy = data.aws_iam_policy_document.backup_uploader.json
}
