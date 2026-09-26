# Costs

**English** | [Español](../es/cost-analysis.md)

The goal is to spend **less than US$0.10 per month** during normal operation. AWS Budget is set to **US$2 per month** to flag unexpected spending, but it is an alert, not a cap that stops charges.

## Initial estimate

With six generations per category and the current measurements, retained backups would use about **2.15 GB**. As a planning reference, S3 Standard in `us-east-1` cost US$0.023 per GB-month when this project was documented:

```text
2.15 GB × US$0.023 ≈ US$0.05 per month
```

This excludes requests, restores, transfers, taxes, and growth. Confirm rates and measure actual bytes before creating the bucket. [S3 pricing](https://aws.amazon.com/s3/pricing/).

## Keeping costs small

| Area | Initial decision |
|---|---|
| Storage | One private S3 Standard bucket |
| Encryption | SSE-S3 |
| Retention | Six sets per category |
| Compute | No permanent EC2 instance |
| Networking | No NAT Gateway, ALB, endpoints, or new domain |
| Managed services | No RDS, ECS, or Fargate |
| Versioning, Object Lock, and a dedicated KMS key | Outside the first version |

Future cloud test environments will be budgeted separately and removed afterward. The first restore will run locally.
