# Course Finder Agent HLD in AWS

## High-Level Design
![CourseFinderHLD](./CourseFinderAgent-HLD.png)




1. Application is deployed to AWS as an **ECR** image with GitHub actions orchestrating the CI/CD workflows. 
2. The Application Load Balancer routes the uses requests to the main app with Gradio as the MVP frontend UI and FastAPI as the backend. Next.js is a planned replacement frontend

3. The full-stack application will run on **Amazon ECS** on **Fargate**. This is based on the assumption that the institution uses a hybrid infrastructure which allow portability to native Kubernetes in on-prem environment. </br> </n>
    3a. The current FastAPI backend uses deterministic regex-based intent routing. In the target architecture, it routes user queries to a LangGraph supervisor agent running on **Amazon ECS**. The supervisor agent acts as the orchestrator that analyses the user queries and determines the appropriate specialized agent to handle the request.
4. In the target architecture, the LangGraph supervisor agent analyses the user query to determine intent and routes it to the appropriate specialized sub-agent based on the request type. Each specialised agent uses a **DynamoDB** based checkpoint saver implementation for LangGraph to maintain conversational context. Only the `Course Tutor Agent` retrieves course material from the Knowledge bases; the `Academic Planning Agent` uses structured academic records for planning.</br>

    4a. The `Academic Planning Agent` handles the queries for student to determine which courses to take based on their enrolment status, degree requirement and course catalog. </br> 
    4b. The `Course Tutor Agent` allows student to understand the learnings from the course materials provided. Bedrock generates an explaination grounded in retrieved material.</br>
    4c. The `Student Context Agent` retrieves student's academic history and current enrolments 
5. **Cloudwatch** metrics enables LLM inference to evaluate model performance
6. **SQS** handles queues for manual uploads by Adminstrators to update the knowledge bases for each specialized agent.



## UI and backend runtime

These two views show the application as it runs locally today. The AWS diagram above remains the deployment target.

### End-to-end view

![UI and backend runtime overview](./docs/diagrams/architecture-overview.svg)

The UI is a Gradio app, not Next.js. It keeps only a session cookie and a CSRF token, then calls the `/api/v1` surface over HTTP.
FastAPI authenticates the session, derives the authorized student scope, and passes that scope into the agent layer.
The supervisor delegates to three specialists, with the tutor using scoped retrieval, the planner using deterministic rules, and the context agent reading only the authorized student record.
The on-demand worker ingests the supplied JSON and PDF fixtures into local SQLite and versioned artefacts.

### Backend detail

![Backend internals: authorized request path](./docs/diagrams/backend-internals.svg)


Authorization runs before any agent tool executes.
The conversation service owns thread state and the user's unit-cap preference, but authoritative academic data is re-read on every turn.
The tutor is the only component that reads reading chunks and figure assets, and those reads are filtered by course and document scope.
The planner calls the deterministic eligibility and degree-rule engine; a model may explain those results but may not change them.

Editable diagram sources: [architecture-overview.html](./docs/diagrams/architecture-overview.html) and [backend-internals.html](./docs/diagrams/backend-internals.html).

## Security and Permission Boundaries

* **WAF** - Web application firewall to prevent SQL injection and XSS
* **ACM** - SSL certifcation for HTTPS and mTLS config


* **Cognito User Pools** - Planned user sign-in and token issuance; token verification remains a pending release task. Server-side application policy checks enforce student and adviser record scope.


* **Secrets Manager** - manages credentials for RDS databases
* **KMS** - manages encryption for data at rest
* **IAM** - role-based access controls and permission policies

## Miscellaneous
- **AWS Amplify** - serves as the entry point for all interactions and validates the request and routes to **AWS Lambda** resolver function for processing
- **DynamoDB** to store sessions data and user interaction history as key-value pairs 
- Another **AWS Lambda** triggers manual uploads from Administrators to S3 bucket and updates Bedrock knowledge bases