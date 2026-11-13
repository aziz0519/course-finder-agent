# Infrastructure

Not deployed yet. This directory records the target so the application is built
deployable, and defines the tiers we will move through.

## Target assumptions

| Item | Assumption |
|---|---|
| Cloud / IaC | AWS, CDK v2 in Python (Terraform would only be adopted if chosen before implementation) |
| Region | `ap-southeast-1` (placeholder in `.env.example`; confirm before deploy) |
| Environments | `dev` now, `prod` only when someone owns its cost and on-call |
| Account | One account; no credentials in CDK context, code, or outputs |
| Data residency | Synthetic fixtures only; no real student PII |

## Tiers

### Tier 0 — local (current)

Single process, no AWS credentials, no containers required:

- `uv run` for the API/worker; SQLite instead of RDS; local filesystem instead of S3;
  local auth adapter instead of Cognito; a deterministic offline model adapter.
- Retrieval uses SQLite FTS5 plus an optional embedding adapter, so pgvector is not a
  prerequisite for the demo.
- This tier is where M0–M5 acceptance happens.

### Tier 1 — demo deployment (~$50/month)

One combined container, one stack, no NAT:

| Resource | Configuration | Why it is enough |
|---|---|---|
| ECS Fargate | 1 task, 0.5 vCPU / 1 GB, public subnet, SG ingress only from the ALB SG | Single writer, demo only |
| ALB | HTTPS listener, HTTP→HTTPS redirect, ACM cert | Only public application ingress |
| RDS PostgreSQL | `db.t4g.micro`, 20 GB gp3, private access | Exercises the real persistence path |
| S3 | One private bucket, public access blocked, encryption on | Source PDFs and derived assets |
| Secrets Manager | DB credentials and session material | Nothing secret in the image or repo |
| CloudWatch | Log groups with retention, basic alarms | Enough to debug a demo |

Cost drivers: Fargate ~$18, ALB ~$18–22, RDS ~$14, plus a few dollars for logs and
storage. `cdk destroy` must leave no orphaned billable resources.

Cheaper variants and why I would not lead with them: SQLite on EFS removes RDS (~$12/mo)
but adds a mount target and backup story; Lightsail containers are ~$7–25/mo but diverge
from the ECS target and complicate RDS/VPC integration.

### Tier 2 — production target (AGENTS.md section 3.1)

Private subnets across two AZs, NAT per AZ, Cognito user pool with `student`/`adviser`/
`admin` groups, three ECS services, WAF, multi-AZ RDS with deletion protection and
automated backups, ECR immutable tags, OIDC-federated CI deployment with an approval
gate. Roughly $200+/month. Not before acceptance passes.

## Invariants kept from day one

- RDS is never publicly accessible; ALB is the only public application ingress.
- S3 blocks all public access and encrypts at rest.
- Separate least-privilege task roles for API, ingestion worker, and frontend.
- No secrets in the repository, CDK context, container image, or frontend bundle.
- Resource tags carry application, environment, owner, and data classification.
- Production data stores have deletion protection and backups before they hold anything.

## Not built yet

`app.py`, `stacks/`, and the CDK assertion tests land in M6, after the data boundary,
IAM roles, and cost estimate have been reviewed. Until then this directory documents
intent only.
