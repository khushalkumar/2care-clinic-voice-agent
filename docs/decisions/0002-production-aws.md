# ADR 0002: Production AWS Deployment

Status: accepted on 2026-07-18.

## Decision

Deploy FastAPI on ECS Fargate behind an HTTPS Application Load Balancer. Use RDS PostgreSQL, SQS with a dead-letter queue, Secrets Manager, CloudWatch, KMS, and Terraform.

The production profile uses two ECS tasks across availability zones and Multi-AZ RDS. A cheaper single-task, single-AZ staging profile is allowed only when identified as non-HA.

## Rejected alternatives

- Lambda adds cold-start, VPC, and database-connection complexity to latency-sensitive tools.
- EC2 requires host maintenance and weaker deployment isolation.
- Render and Railway do not demonstrate the target company's AWS stack.
- App Runner is unavailable to new AWS customers.
