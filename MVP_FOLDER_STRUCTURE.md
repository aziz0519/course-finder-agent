# Recommended MVP Repository Structure

The MVP should use a **monorepo with a modular Python backend**, a separate Next.js frontend, and AWS CDK infrastructure. Keep the agents as modules inside one backend codebase rather than deploying each agent as its own microservice. The API and ingestion worker can run as separate ECS Fargate tasks from the same backend image with different commands.

```text
course-finder-agent/
├── AGENTS.md                         # Project instructions, architecture and agent boundaries
├── README.md                         # Setup, run, test and deploy instructions
├── .gitignore
├── .env.example                      # Local-only variable names; never commit secrets
├── docker-compose.yml                # Local web, API, worker and PostgreSQL development stack
├── Makefile                          # Common developer commands
│
├── apps/
│   ├── web/                          # Next.js + TypeScript frontend
│   │   ├── app/
│   │   │   ├── (auth)/login/page.tsx
│   │   │   ├── (student)/dashboard/page.tsx
│   │   │   ├── chat/[conversationId]/page.tsx
│   │   │   ├── courses/[courseId]/page.tsx
│   │   │   ├── layout.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── chat/                 # Chat panel, messages, citations
│   │   │   ├── courses/              # Course cards, prerequisites, term labels
│   │   │   └── layout/               # Navigation and shared layouts
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── chat/
│   │   │   ├── course-catalog/
│   │   │   └── degree-progress/
│   │   ├── lib/                      # API client, Cognito/session helpers
│   │   ├── types/                    # Generated API types; do not hand-maintain duplicates
│   │   ├── tests/
│   │   ├── package.json
│   │   └── Dockerfile
│   │
│   └── backend/                      # FastAPI API and ingestion worker codebase
│       ├── app/
│       │   ├── main.py               # FastAPI application entry point
│       │   ├── api/v1/
│       │   │   ├── router.py
│       │   │   └── routes/
│       │   │       ├── chat.py
│       │   │       ├── students.py
│       │   │       ├── courses.py
│       │   │       ├── degree_progress.py
│       │   │       └── admin_ingestion.py
│       │   ├── core/
│       │   │   ├── config.py         # Typed settings and environment configuration
│       │   │   ├── logging.py
│       │   │   ├── security.py       # JWT validation and security helpers
│       │   │   └── errors.py
│       │   ├── authz/
│       │   │   ├── dependencies.py   # Authenticated-user and role dependencies
│       │   │   └── policies.py       # Student/adviser/admin access policies
│       │   ├── domain/               # Deterministic business rules; no LLM dependency
│       │   │   ├── students/
│       │   │   ├── courses/
│       │   │   ├── prerequisites/
│       │   │   └── degree_requirements/
│       │   ├── agents/
│       │   │   ├── supervisor/
│       │   │   │   ├── graph.py
│       │   │   │   ├── routing.py
│       │   │   │   └── state.py
│       │   │   ├── student_context/
│       │   │   │   ├── agent.py
│       │   │   │   ├── prompts.py
│       │   │   │   └── tools.py
│       │   │   ├── course_tutor/
│       │   │   │   ├── agent.py
│       │   │   │   ├── prompts.py
│       │   │   │   └── tools.py
│       │   │   ├── academic_planner/
│       │   │   │   ├── agent.py
│       │   │   │   ├── prompts.py
│       │   │   │   └── tools.py
│       │   │   ├── shared/
│       │   │   │   ├── schemas.py     # Typed agent input/output contracts
│       │   │   │   ├── tool_registry.py
│       │   │   │   └── policies.py    # Agent-level scope and tool restrictions
│       │   │   └── workflows/
│       │   │       ├── tutoring.py
│       │   │       └── course_recommendation.py
│       │   ├── rag/
│       │   │   ├── chunking.py
│       │   │   ├── embeddings.py
│       │   │   ├── retrieval.py
│       │   │   └── citations.py       # Source document and page provenance
│       │   ├── ingestion/
│       │   │   ├── jobs.py            # Worker entry points
│       │   │   ├── pdf_parser.py      # PDF text, layout, tables, figures, equations
│       │   │   ├── json_loader.py
│       │   │   ├── validation.py
│       │   │   ├── normalization.py
│       │   │   └── pipeline.py
│       │   ├── db/
│       │   │   ├── session.py
│       │   │   ├── base.py
│       │   │   └── models/            # SQLAlchemy persistence models
│       │   ├── repositories/          # Authorized data-access boundary
│       │   ├── services/              # Application use cases and orchestration
│       │   └── worker.py              # SQS/S3 ingestion worker entry point
│       ├── migrations/                # Alembic database migrations
│       ├── tests/
│       │   ├── unit/
│       │   ├── integration/
│       │   ├── agents/
│       │   └── security/
│       ├── pyproject.toml
│       └── Dockerfile                 # Same image can start API or worker command
│
├── infrastructure/
│   └── cdk/                           # AWS CDK v2 in Python
│       ├── app.py
│       ├── cdk.json
│       ├── requirements.txt
│       ├── config/
│       │   ├── dev.json
│       │   └── prod.json
│       ├── stacks/
│       │   ├── network_stack.py       # VPC, subnets and security groups
│       │   ├── security_stack.py      # Cognito, IAM roles and KMS keys
│       │   ├── data_stack.py          # S3, RDS PostgreSQL/pgvector and SQS
│       │   ├── application_stack.py   # ECR, ECS Fargate, ALB and services
│       │   └── monitoring_stack.py    # CloudWatch logs, metrics and alarms
│       ├── constructs/                # Reusable CDK constructs, if needed
│       └── tests/                     # CDK assertions and infrastructure tests
│
├── data/
│   ├── samples/                       # Supplied synthetic fixtures; no real student data
│   │   ├── course-catalog.json        # 14 courses, term policies and BSc Physics requirements
│   │   ├── student-records.json       # student-001 and student-002 academic snapshots
│   │   └── course-materials/          # Five catalogue-referenced PDFs (file bytes pending)
│   ├── schemas/
│   │   ├── course_catalog.schema.json
│   │   ├── degree_requirements.schema.json
│   │   └── student_records.schema.json
│   └── README.md                      # Dataset provenance, expected format and handling
│
├── scripts/
│   ├── validate_datasets.py
│   ├── seed_dev_data.py
│   ├── bootstrap_local.sh
│   └── generate_api_types.sh          # Generate TypeScript client/types from OpenAPI
│
├── docs/
│   ├── architecture/
│   │   ├── aws-context-diagram.mmd
│   │   └── aws-deployment-diagram.mmd
│   ├── agent-boundaries.md
│   ├── data-model.md
│   ├── ingestion-and-rag.md
│   ├── security-and-rbac.md
│   └── decisions/                     # Short architecture decision records
│
├── tests/
│   └── e2e/                           # End-to-end API/UI workflows
│
└── .github/
    └── workflows/
        ├── ci.yml                     # Lint, type-check, tests and CDK assertions
        └── deploy.yml                 # OIDC-based AWS deployment
```

## MVP implementation boundaries

1. **One backend codebase, distinct runtime processes.** Keep FastAPI, agent modules, RAG and ingestion code together initially. Run the API and ingestion worker as separate ECS Fargate tasks from the same image. Do not create one microservice per agent.
2. **Enforce authorization before retrieval.** The API validates the Cognito JWT and RBAC policy. Repositories apply student/adviser row-level scope before returning data to any agent. Agents must not connect directly to the database with unrestricted credentials.
3. **Keep academic decisions deterministic.** Prerequisite validation, term-offering checks, degree audits and eligibility calculations belong in `domain/`. The Academic Planning Agent explains and ranks the deterministic result; it does not override it.
4. **Keep source provenance.** Store source document ID, page number and relevant chunk/figure metadata through ingestion and retrieval so tutor answers can cite evidence. Treat missing evidence as unknown, not as an invitation to guess.
5. **Use S3 for original documents and PostgreSQL for queryable data.** Keep original PDFs/JSON in S3; store normalized academic records, conversation state, reading metadata and pgvector embeddings in PostgreSQL for the MVP.
6. **Generate frontend types from the backend contract.** Use FastAPI's OpenAPI schema to generate TypeScript API types/client code rather than maintaining two independent definitions.
7. **Separate environment configuration from secrets.** Commit only `.env.example` placeholders. Use AWS Secrets Manager/SSM for deployed secrets and distinct CDK configuration for dev and prod.

## Suggested build order

1. Repository scaffold, Docker Compose, configuration and dataset JSON schemas.
2. PostgreSQL models/migrations, ingestion validation and seed data.
3. Cognito JWT validation, RBAC policies and scoped repository methods.
4. Course Tutor RAG workflow with page citations.
5. Student Context Agent and conversation persistence.
6. Deterministic degree audit and Spring 2027 course eligibility service.
7. Academic Planning Agent and supervisor routing.
8. Next.js chat/dashboard experience and end-to-end tests.
9. CDK stacks, CI/CD deployment and CloudWatch monitoring.


### Supplied catalogue fixture

The supplied catalogue and degree requirements are stored at `data/samples/course-catalog.json`; the two synthetic academic snapshots are stored at `data/samples/student-records.json`. The student-record schema is at `data/schemas/student_records.schema.json`. The five catalogue reading references resolve under `data/samples/course-materials/`; the PDF file bytes are still pending.
