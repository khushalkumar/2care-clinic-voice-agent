# Deployment, migration, and rollback

1. Confirm CI, image scan, tests, and OpenTofu validation are green for the commit SHA.
2. Confirm the AWS account is fully verified and the selected deployment identity can use ECR, ECS, RDS, ALB, Secrets Manager, IAM, CloudWatch, and ACM.
3. Publish an immutable image to ECR and set `container_image` to its commit-SHA tag. Do not create the stack with a placeholder image.
4. Create the application secret value out of band with `REQUEST_HMAC_SECRET`, `AVAILABILITY_TOKEN_SECRET`, Cliniko credentials, and the encrypted phone-to-Cliniko-ID mapping. Never put those values in Terraform, Git, or a committed environment file.
5. Review `tofu plan`; confirm no secret value or destructive database action appears.
6. Obtain explicit approval before creating or changing billable AWS resources.
7. Apply infrastructure, verify IAM access, and run `alembic upgrade head` as a one-off task. Stop if migration fails.
8. Deploy the immutable image SHA. Wait for healthy ALB targets and steady ECS tasks.
9. Check `/live`, `/ready`, logs, 5xx, DLQ, and database connections.
10. Run one synthetic search/book/cancel canary and verify PostgreSQL plus PMS state.
11. Create and test the Bolna agent against the HTTPS tool endpoint. Route the voice number only after the backend canary passes.

Rollback the ECS service to the previous task definition if application health regresses. Do not
blindly downgrade schema. Prefer a forward fix; use Alembic downgrade only when that exact
migration was rehearsed and no newer code wrote incompatible data. Preserve DLQ messages and
reconcile `pending_verification` operations before reopening booking.
