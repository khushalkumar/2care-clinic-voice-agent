# Terraform

Terraform defines staging and production AWS profiles after the application contracts and database migrations are stable. Staging uses an ALB-only public Fargate task to avoid NAT Gateway cost; production uses private tasks with per-AZ NAT gateways. No billable infrastructure is created without explicit approval.
