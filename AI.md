# AI.md --- Multi-Agent System Workflow

## 1. Purpose and scope

The Student Learning and Academic Planning Assistant helps students
understand enrolled-course material using supplied readings and plan
subsequent courses using their academic records, course catalogue,
prerequisites, term availability, and degree requirements.

The sample scenario treats **Fall 2026** as the current term and
**Spring 2027** as the next term. The catalogue sets an institutional
maximum of **16 units per term** and states that a course in progress in
Fall 2026 counts toward prerequisites for courses in the following term.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:42f66e6f17822c4b1cb27a4bffaaf0d6a62ecae793e700f410719e29b7207d47 -->

The current MVP uses a lightweight **Gradio UI** and a modular Python
backend with deterministic regex-based intent routing to specialist
functions. **LangGraph** orchestration and **Amazon Bedrock** model
inference are target architecture components; neither is currently
implemented or declared as a dependency. PostgreSQL/pgvector for structured
and retrieval data and S3 for source documents and visual assets are also
target components. Agents are logical responsibility boundaries; they do
not need to be independently deployed services in the MVP.

<!-- /coderabbit-ai-generated:v1 -->

The assistant provides advice, not official registration or changes to
academic records.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:54e7c68e3d4ac8fe873067038779e85d0926c85f0c20562acc2e9cea21ee1681 -->

## 2. Target components and agent boundaries

<!-- /coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:79c6a0f6b890634b50d8fd35ebcb510374c525d2afd79c607b3a92f8960a78e8 -->

| Component | Responsibility | Boundary |
| --- | --- | --- |
| Gradio UI | Collect user messages and display answers, citations, and recommendations | Presentation only; not an authorization boundary |
| Application API | Validate requests, establish trusted identity context, invoke workflows, return responses | Enforces access before sensitive data reaches an agent |
| Authentication / RBAC guard | Authenticate the user and authorize role and record-level scope | Deterministic; never delegated to an LLM |
| LangGraph Supervisor | Classify intent, route to a specialist, coordinate results | Does not independently invent academic rules |
| Student Context service/agent | Retrieve the authorized student's programme, completions, enrolments, and adviser relationship | Returns only data permitted by the authorization context |
| Course Tutor agent | Answer questions grounded in course readings | Must use retrieved evidence and citations; must disclose insufficient evidence |
| Academic Planning agent | Explain degree progress and propose next-term course combinations | Uses deterministic domain services for eligibility and unit calculations |
| Academic Rules Engine | Evaluate prerequisites, terms offered, degree requirements, and unit limits | Authoritative for calculations; no LLM-based eligibility decisions |
| Retrieval service | Search extracted reading chunks and associated visual evidence | Returns source metadata and evidence references |
| Conversation state store | Preserve history, preferences, and source references between turns | Context only; not an authoritative academic record |

<!-- /coderabbit-ai-generated:v1 -->

### Boundary principles

-   Each agent receives only the context and tools needed for its task.
-   Student-specific retrieval is scoped using the authenticated user's
    authorization.
-   The LLM may explain a rules-engine result but cannot override it.
-   The Tutor must not fabricate facts, page numbers, figures, or
    citations.
-   Completed and in-progress courses remain distinct statuses.
-   A user-requested unit cap is a conversational preference; it does
    not alter the catalogue's institutional maximum.
-   If the supplied data cannot answer a question, the assistant says so
    rather than guessing.

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:a17d2a94db4528369848d76f6532b675f282561d766ca9fd83b7b6c7cb3d232e -->

## 3. Target runtime system overview

<!-- /coderabbit-ai-generated:v1 -->

``` mermaid
flowchart TD
    U[Student] --> UI[Gradio UI]
    UI --> API[Application API]
    API --> AUTH[Authentication and RBAC]
    AUTH -->|Denied| DENY[401 / 403]
    AUTH -->|Authorized context| STATE[(Conversation state)]
    STATE --> SUP[LangGraph Supervisor]

    SUP -->|Course question| TUTOR[Course Tutor]
    SUP -->|Planning question| PLAN[Academic Planning]
    SUP --> CTX[Student Context service]

    TUTOR --> RAG[Hybrid retrieval]
    RAG --> VDB[(PostgreSQL + pgvector)]
    RAG --> S3[(S3 PDFs and visual assets)]
    TUTOR --> BEDROCK[Amazon Bedrock]

    PLAN --> CTX
    CTX --> DB[(PostgreSQL academic records)]
    PLAN --> RULES[Deterministic Academic Rules Engine]
    RULES --> DB
    PLAN --> BEDROCK

    TUTOR --> SUP
    PLAN --> SUP
    SUP --> STATE
    SUP --> API
    API --> UI
```

For the MVP, the API, Supervisor, agents, retrieval code, and rules
engine can run in one application container. Run ingestion separately
because PDF processing can be resource-intensive and should not block
interactive requests.

## 4. First message to response

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:97c4e79f3043d6f756d80da9ec8f2755a38728014d36d2c99d038e78295fcb70 -->

1.  **Message submission:** The student submits a question in Gradio.
    The request includes the message, conversation ID when continuing a
    conversation, and session credential.
2.  **Authentication:** The backend validates the session/token and
    constructs a trusted identity context. The UI must not be trusted to
    assert its own student ID or role.
3.  **Authorization:** The RBAC guard determines the user's role and
    permitted student-record scope. A student can access their own
    record; an adviser must be checked against adviser assignments;
    administrative ingestion requires an administrator role.
4.  **Conversation loading:** Before loading an existing conversation's
    messages or references, verify that the authenticated user is authorized
    to access that conversation. Check student ownership and recheck its
    current authorized student-record scope, including any changes to
    adviser assignments or access. If the check fails, deny access and do
    not load history or references. Only after it succeeds, load relevant
    messages, active course/reading references, figure/page references,
    planning term, and user preferences such as a requested unit cap.

5.  **Intent classification:** The Supervisor classifies the request and
    routes it to the Tutor, Planner, or a clarification/unsupported
    path.
6.  **Specialist execution:** The selected specialist obtains only the
    data and tools required for its task.
7.  **Evidence and policy checks:** Validate citations, source
    references, academic rule outputs, and limitations before composing
    the final response.
8.  **Persistence and response:** Store the new turn and relevant
    references in conversation state, then return a structured response
    to Gradio.

<!-- /coderabbit-ai-generated:v1 -->

Re-check authorization on every turn. Conversation history does not
grant access to data.

## 5. Course tutoring workflow

Example initial question:

> How does the Bohr model explain the lines in the hydrogen spectrum?

1.  The Supervisor routes the request to the Course Tutor.
2.  The Tutor resolves the relevant enrolled course using authorized
    student context. In the sample records, `student-001` is enrolled in
    PHYS 350 in Fall 2026, and the catalogue associates the Bohr model
    reading with PHYS 350.
3.  The retrieval service searches the course reading using lexical and
    vector retrieval, filtered by course/document metadata.
4.  It returns relevant chunks, document ID, page numbers, section
    headings, and related figure/asset identifiers.
5.  The Tutor generates an explanation grounded in the retrieved
    evidence.
6.  The response cites the original reading and page. If evidence is
    insufficient, the Tutor states the limitation or asks a
    clarification.

### Visual follow-up

Example:

> According to the diagram in that reading, how many electrons can the
> second energy level hold?

1.  Load the previous turn's reading reference from conversation state.
2.  Resolve "that reading" to the actual document previously discussed.
3.  Retrieve the relevant figure crop or rendered page, page number,
    caption, and nearby text.
4.  If needed, use a vision-capable model to interpret the image
    alongside extracted text.
5.  Check that the retrieved figure supports the answer and cite its
    page/figure.
6.  If the figure cannot be located or interpreted reliably, say so. A
    familiar fact from general knowledge is not sufficient to pass this
    evidence-grounded test.

### Tutoring sequence diagram

``` mermaid
sequenceDiagram
    autonumber
    actor Student
    participant UI as Gradio
    participant API as Application API
    participant RBAC as Auth / RBAC
    participant State as Conversation State
    participant Sup as LangGraph Supervisor
    participant Ctx as Student Context
    participant Tutor as Course Tutor
    participant RAG as Retrieval Service
    participant DB as PostgreSQL + pgvector
    participant S3 as S3 Visual Assets
    participant LLM as Bedrock

    Student->>UI: Ask course question
    UI->>API: Message + conversation ID + session
    API->>RBAC: Authenticate and authorize
    RBAC-->>API: Trusted access context
    API->>State: Load history and references
    State-->>API: Conversation context
    API->>Sup: Message + trusted context
    Sup->>Tutor: Route tutoring request
    Tutor->>Ctx: Resolve course and reading
    Ctx-->>Tutor: Authorized course context
    Tutor->>RAG: Search reading
    RAG->>DB: Hybrid search with metadata filters
    DB-->>RAG: Chunks and source references
    RAG-->>Tutor: Text, pages, figure references
    opt Visual evidence needed
        Tutor->>S3: Fetch page render or figure crop
        S3-->>Tutor: Visual evidence
        Tutor->>LLM: Interpret visual with nearby text
        LLM-->>Tutor: Visual interpretation
    end
    Tutor->>LLM: Generate grounded explanation
    LLM-->>Tutor: Answer draft
    Tutor->>Tutor: Verify evidence and citations
    Tutor-->>Sup: Answer + citations + limitations
    Sup->>State: Persist turn and references
    Sup-->>API: Final response
    API-->>UI: Answer and citations
    UI-->>Student: Display response
```

## 6. Academic planning workflow

Example:

> What should I take in Spring 2027 to progress my degree? Keep it to 12
> units.

1.  The Supervisor routes the request to the Academic Planning agent.
2.  The Planner obtains the authorized student's programme, completed
    courses, current enrolments, and relevant adviser assignment.
3.  It retrieves the course catalogue and programme requirements.
4.  The Academic Rules Engine evaluates:
    -   Courses offered in Spring 2027.
    -   Prerequisite satisfaction.
    -   The policy allowing Fall 2026 in-progress courses to count for
        Spring 2027 prerequisites.
    -   Outstanding degree requirements.
    -   The institutional 16-unit maximum.
    -   The student's lower requested 12-unit cap.
5.  The Planner ranks feasible combinations using explicit criteria,
    such as advancing outstanding core requirements.
6.  The LLM explains the result; it does not calculate eligibility.
7.  The response includes courses, total units, eligibility rationale,
    requirements advanced, exclusions, and any conditions.

### Deterministic planning rules

-   Current term is Fall 2026; next term is Spring 2027.
-   Institutional maximum is 16 units.
-   A course in progress in Fall 2026 can satisfy a prerequisite for
    Spring 2027.
-   A course must be offered in Spring to be considered for Spring 2027.
-   In-progress courses are not reported as completed.
-   Prerequisites and degree requirements are separate evaluations.
-   A lower user-requested cap is allowed; it does not change the
    institutional policy.

### Planning follow-up

Example:

> I have accepted a part-time internship, so cap me at 8 units.

The application restores the same student and Spring 2027 context,
updates the conversation's requested cap from 12 to 8, and reruns the
deterministic rules engine. It explains what changed and which courses
were deferred. The 8-unit cap is a temporary planning preference, not a
change to the official student record or institutional 16-unit maximum.

### Academic planning sequence diagram

``` mermaid
sequenceDiagram
    autonumber
    actor Student
    participant UI as Gradio
    participant API as Application API
    participant RBAC as Auth / RBAC
    participant State as Conversation State
    participant Sup as Supervisor
    participant Planner as Academic Planner
    participant Ctx as Student Context
    participant DB as PostgreSQL
    participant Rules as Academic Rules Engine
    participant LLM as Bedrock

    Student->>UI: Request Spring 2027 plan, cap 12
    UI->>API: Message + conversation ID
    API->>RBAC: Authenticate and authorize
    RBAC-->>API: Authorized context
    API->>State: Load history and preferences
    State-->>API: Conversation context
    API->>Sup: Planning request
    Sup->>Planner: Delegate planning
    Planner->>Ctx: Retrieve authorized student profile
    Ctx->>DB: Read programme, completions, enrolments
    DB-->>Ctx: Academic data
    Ctx-->>Planner: Student context
    Planner->>DB: Read catalogue and degree requirements
    DB-->>Planner: Course and programme rules
    Planner->>Rules: Evaluate eligibility and 12-unit cap
    Rules-->>Planner: Feasible courses and requirement gaps
    Planner->>LLM: Explain plan and rationale
    LLM-->>Planner: Explanation
    Planner-->>Sup: Recommendations and rule evidence
    Sup->>State: Save plan and cap 12
    Sup-->>API: Recommendation
    API-->>UI: Plan and rationale
    UI-->>Student: Display plan

    Student->>UI: Follow-up: reduce cap to 8
    UI->>API: Follow-up + same conversation ID
    API->>RBAC: Revalidate authorization
    RBAC-->>API: Authorized context
    API->>State: Load previous plan and preference
    State-->>API: Spring 2027 context, cap 12
    API->>Sup: Updated request
    Sup->>Planner: Recalculate with cap 8
    Planner->>Rules: Re-evaluate same records with cap 8
    Rules-->>Planner: Revised feasible combination
    Planner->>LLM: Explain changes and deferred courses
    LLM-->>Planner: Updated explanation
    Planner-->>Sup: Revised plan
    Sup->>State: Save updated cap 8
    Sup-->>API: Revised recommendation
    API-->>UI: Updated plan
    UI-->>Student: Display revised plan
```

## 7. Response contract and evidence

An internal response can use a structured shape such as:

``` json
{
  "answer": "Student-facing explanation",
  "intent": "course_tutoring",
  "citations": [
    {
      "document_id": "phys350-bohr-model",
      "page": 2,
      "content_type": "figure",
      "asset_id": "resolved-asset-id"
    }
  ],
  "limitations": [],
  "conversation_updates": {
    "active_course": "PHYS 350"
  }
}
```

This is illustrative. Actual identifiers and page numbers must come from
the ingestion manifest and retrieval results; do not hard-code them.

Before display, check that: - The answer addresses the question. -
Student-specific statements are supported by authorized data. - Reading
claims cite retrieved chunks and original pages. - Visual answers use
the actual figure/page evidence. - Planning calculations come from the
rules engine. - Missing facts and assumptions are explicit.

Planning responses should additionally include target term, requested
cap, total units, course codes, eligibility evidence, and requirements
advanced.

## 8. Failure handling

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:9097e06251eb63755ca3fd30155e7b34731b0778b8d4d1d6d3bcebc1eb76df0d -->

| Condition | Expected behaviour |
| --- | --- |
| Invalid/expired session | Require re-authentication |
| Student requests another student's record | Deny before retrieval |
| No matching reading | State that supplied material does not answer the question |
| Diagram cannot be verified | State limitation; do not guess |
| Missing/inconsistent student data | Identify missing data; avoid definitive recommendation |
| Prerequisite not met | Exclude course and explain why |
| Requested cap exceeds institutional maximum | Apply maximum and explain constraint |
| No feasible plan under cap | Explain conflict and request a revised constraint |
| Model/retrieval unavailable | Return controlled error, not fabricated content |
| Tool failure | Bounded retry and record failure |

<!-- /coderabbit-ai-generated:v1 -->

## 9. Guardrails and security

-   Authenticate and authorize in application code, not in prompts.
-   Treat messages, PDFs, extracted text, and tool outputs as untrusted.
-   Separate system instructions from retrieved document content.
-   Give each agent only the tools it needs.
-   Enforce academic rules deterministically.
-   Restrict outbound URL fetching to approved schemes and allowlisted
    domains; block internal, loopback, link-local, and cloud metadata
    destinations.
-   Apply model content filtering and domain-specific safety rules.
-   Validate structured outputs and citations before display.
-   Log security events without unnecessarily logging sensitive student
    data.
-   Encrypt data in transit and at rest; store secrets in managed secret
    storage.

The PHYS 230 reading concerns nuclear physics. Support appropriate
educational explanations, but refuse operational instructions that would
facilitate construction or optimisation of a weapon.

## 10. MVP to production

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:2ef600e3f4956178d5b7c636b9f7d6a0ec5e8f09241b274c1f9fb2a1c8d52450 -->

**MVP** - Gradio UI and one modular Python backend with deterministic
regex-based intent routing and logically specialised agents. - LangGraph
Supervisor and Bedrock model inference remain target components; neither
is currently implemented or declared as a dependency. - PostgreSQL with pgvector. - S3 for original PDFs and
processed visual assets. - Basic authentication and RBAC. - Separate
ingestion worker where practical. - AWS CDK v2 provisioning.

<!-- /coderabbit-ai-generated:v1 -->

**Production evolution** - Integrate the institution's portal, SSO, and
authoritative SIS/LMS APIs. - Scale interactive APIs and ingestion
workers independently. - Add queue-based ingestion, retries, dead-letter
handling, and reprocessing. - Improve retrieval with metadata filters,
hybrid search, reranking, and evaluation. - Introduce governed
MCP-compatible tools when multiple systems need standardised tool
access. - Add multi-AZ resilience, tested backups/restore, DR
objectives, observability, and cost controls. - Evaluate managed agent
runtime options if operational needs justify them.

## 11. Acceptance tests

<!-- coderabbit-ai-generated:v1 -->

<!-- coderabbit-ai-generated-section:v1:6fc6a2c4d3884e8c155504ddd910ce295f02d79753c17951be361a3cd5dcfc77 -->

| Test | Required behaviour |
| --- | --- |
| "How does the Bohr model explain the lines in the hydrogen spectrum?" | Retrieve PHYS 350 reading and return grounded explanation with citations |
| "According to the diagram in that reading, how many electrons can the second energy level hold?" | Resolve prior reading and verify answer against actual diagram |
| "What should I take in Spring 2027 to progress my degree? Keep it to 12 units." | Produce a feasible plan within 12 units using student-001 and supplied policies |
| "I have accepted a part-time internship, so cap me at 8 units." | Preserve term/student context, update cap, and recompute plan |

<!-- /coderabbit-ai-generated:v1 -->

Tests must validate evidence, calculations, authorization, and persisted
follow-up state, not just response wording.
