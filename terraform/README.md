# Terraform

**English** | [Español](README.es.md)

This directory defines the first offsite-backup resources:

- One private S3 Standard bucket in `us-east-1`.
- SSE-S3 encryption and public access blocking.
- A dedicated IAM user with access limited to backup prefixes.
- No permission for the uploader to delete objects.
- Lifecycle expiration after 91 days for critical sets and 183 days for Plex monthly metadata.
- Versioning left off to keep the initial storage model simple.

Terraform does not create an access key. Create it in the AWS console only after the plan is approved, then store it directly on each VM. Never commit it, paste it into a terminal history, or include it in Terraform variables.

## Before applying

This module creates the bucket and limited uploader identity in AWS.

1. Install Terraform and sign in to AWS with an administrator account.
2. Copy `terraform.tfvars.example` to `terraform.tfvars` and set a globally unique `bucket_name`.
3. Run `terraform init` and `terraform plan`.
4. Check the plan: it should create only the bucket security settings, lifecycle configuration, IAM user, and inline policy. It must not create a Budget, EC2 instance, network resource, or access key.
5. Apply only after reviewing the plan.

Lifecycle rules work by object age, so they retain approximately six 15-day sets and six monthly Plex sets; S3 can remove an object shortly after its expiration date. The home VMs do not receive object-deletion permission.

`terraform.tfvars`, state files, plans, and credentials are excluded by `.gitignore`. Commit `.terraform.lock.hcl` after the first successful `terraform init`.

See [costs](../docs/en/cost-analysis.md) and [backup strategy](../docs/en/backup-strategy.md).
