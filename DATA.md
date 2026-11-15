# DATA.md -- Data Pipelines Walkthrough

## 1. Purpose and scope

This document describes ingestion, validation, transformation, storage,
and retrieval for the Student Learning and Academic Planning Assistant.

The sample datasets are: 1. Five course-reading PDFs, approximately
9--17 pages each, containing text, photographs, diagrams, charts,
tables, and equations. 2. A JSON course catalogue and degree
requirements dataset containing 14 courses and the Bachelor of Science
in Physics requirements. 3. A JSON student records dataset containing
two synthetic students, their programme, completed courses, current
enrolments, and adviser assignments.

The sample scenario defines Fall 2026 as the current term and Spring
2027 as the next term.

Keep four data classes separate: - Immutable original source files. -
Parsed and enriched document artefacts. - Searchable text chunks and
embeddings. - Structured academic records used by deterministic
planning.

Conversation history and preferences are a fifth, separate class. They
are not authoritative academic records.

## 2. Source datasets

  ------------------------------------------------------------------------
  Dataset           Format            Use                MVP source of
                                                         truth
  ----------------- ----------------- ------------------ -----------------
  Course readings   PDF               Grounded course    Original PDF in
                                      tutoring           S3

  Course catalogue  JSON              Course details,    Validated
                                      units,             relational
                                      prerequisites,     representation
                                      terms              plus retained
                                                         source JSON

  Degree            JSON section of   Degree progress    Validated
  requirements      catalogue         and elective/core  relational
                                      rules              representation
                                                         plus retained
                                                         source JSON

  Student records   JSON              Student-specific   Validated
                                      planning           relational
                                                         representation
                                                         plus retained
                                                         source JSON
  ------------------------------------------------------------------------

The supplied files are authoritative inputs for the MVP. In production,
SIS, catalogue, and degree-audit systems may be authoritative, but their
existence and integration interfaces must be confirmed with the
institution.

### 2.1 Catalogue facts

The supplied catalogue specifies: - Current term: `Fall 2026`. - Next
term: `Spring 2027`. - Maximum units per term: `16`. - A course in
progress in Fall 2026 counts toward prerequisites for courses in the
following term. - 14 courses and one programme:
`bachelor-of-science-physics`.

The programme requirements include Physics core, Physics electives,
Literature, History, and Capstone rules. Load these rules as structured
data; do not rely on an LLM prompt as their only representation.

### 2.2 Student record facts

The synthetic fixture contains: - `student-001`: Sophomore; PHYS 230 and
HIST 250 completed in Fall 2025; PHYS 350, HIST 210, and ENGL 120
enrolled in Fall 2026. - `student-002`: Freshman; no completed courses
listed; HIST 250 and ENGL 120 enrolled in Fall 2026.

Do not infer grades, transfer credits, additional course outcomes, or
student attributes not present in the files.

## 3. End-to-end data pipeline

``` mermaid
flowchart TD
    subgraph Sources["Source datasets"]
        PDF[Five course-reading PDFs]
        CAT[Course catalogue and degree requirements JSON]
        STU[Student records JSON]
    end

    subgraph Landing["Landing and source preservation"]
        RAW[(S3 raw / versioned objects)]
        MAN[Manifest, checksums, source metadata]
    end

    subgraph Processing["Validation and transformation"]
        ROUTER[File type router]
        DOC[Layout-aware PDF extraction]
        VIS[Page rendering and visual enrichment]
        CHUNK[Page-aware semantic chunking]
        SCHEMA[JSON schema validation]
        REF[Cross-reference validation]
        EMB[Embedding generation]
    end

    subgraph Stores["Application data stores"]
        ASSET[(S3 processed pages and figure assets)]
        PG[(PostgreSQL academic records)]
        VEC[(pgvector chunks and embeddings)]
        JOB[(Ingestion status and audit metadata)]
    end

    subgraph Consumers["Runtime consumers"]
        TUTOR[Course Tutor retrieval]
        PLANNER[Academic Planning services]
    end

    PDF --> RAW
    CAT --> RAW
    STU --> RAW
    RAW --> MAN --> ROUTER

    ROUTER -->|PDF| DOC --> VIS --> CHUNK --> EMB --> VEC
    VIS --> ASSET
    CHUNK --> VEC

    ROUTER -->|Catalogue JSON| SCHEMA
    ROUTER -->|Student JSON| SCHEMA
    SCHEMA --> REF --> PG

    MAN --> JOB
    DOC --> JOB
    SCHEMA --> JOB
    REF --> JOB
    EMB --> JOB

    VEC --> TUTOR
    ASSET --> TUTOR
    PG --> PLANNER
```

PDF and JSON processing are separate paths: reading material is
unstructured and multimodal; academic records are structured and require
schema and referential-integrity validation.

## 4. Ingestion orchestration

A production-oriented AWS pattern is: - S3 stores original and processed
objects. - An ingestion API or administrative process registers a
dataset. - SQS queues processing jobs. - An ECS Fargate worker processes
PDFs and JSON. - PostgreSQL stores structured records, document
metadata, chunks, and vectors. - Ingestion status records and a
dead-letter queue support monitoring and failure handling.

For local development, the same processing functions can be invoked
through a CLI. Keep processing logic independent of the trigger
mechanism.

### Ingestion sequence diagram

``` mermaid
sequenceDiagram
    autonumber
    actor Admin as Dataset publisher
    participant API as Ingestion API / CLI
    participant S3 as Amazon S3
    participant SQS as Amazon SQS
    participant Worker as ECS Fargate worker
    participant Proc as PDF / JSON processors
    participant DB as PostgreSQL + pgvector
    participant Status as Ingestion status

    Admin->>API: Submit source file
    API->>S3: Store original object
    S3-->>API: Object key and version
    API->>Status: Create ingestion job
    API->>SQS: Publish job reference
    API-->>Admin: Job accepted

    SQS->>Worker: Deliver job
    Worker->>S3: Read original object
    S3-->>Worker: File bytes
    Worker->>Proc: Detect type and process

    alt PDF reading
        Proc->>Proc: Extract layout, text, tables and figures
        Proc->>Proc: Render pages and enrich visual regions
        Proc->>Proc: Create page-aware chunks
        Proc->>DB: Store metadata, chunks and embeddings
    else Catalogue or student JSON
        Proc->>Proc: Validate schema
        Proc->>Proc: Validate references and constraints
        Proc->>DB: Upsert validated records
    end

    DB-->>Worker: Persist result
    Worker->>Status: Mark READY / NEEDS_REVIEW / FAILED
    Worker-->>SQS: Acknowledge completed job
    Status-->>Admin: Publish ingestion result
```

## 5. PDF course-reading pipeline

### 5.1 Preflight and preservation

For each PDF: 1. Assign a stable document ID based on course and
reading, e.g. `phys230-critical-mass`. 2. Record filename, course code,
title, checksum, file size, page count, source version, and ingestion
timestamp. 3. Preserve the original PDF in S3 without modification. 4.
Detect native text, scanned pages, or mixed content. 5. Record parser
version and processing status.

The original PDF is the citation authority. Every extracted chunk,
description, and visual asset must be traceable to the source document
and page.

### 5.2 Layout-aware extraction

Use a layout-aware processor such as Docling as the initial extraction
component. Extract where supported: - Headings and section hierarchy. -
Paragraphs and reading order. - Page numbers. - Tables and row/column
structure. - Figure/image regions and captions. - Nearby explanatory
text. - Mathematical expressions. - Bounding boxes and layout
information.

Apply OCR to pages or regions without usable native text. Avoid OCR on
every page when reliable native text is available.

A generic image extractor alone is insufficient: it can return duplicate
image payloads and may not preserve dependable page placement. Keep page
renders and region coordinates as first-class evidence.

### 5.3 Visual enrichment

Because the readings contain photographs, diagrams, charts, tables, and
equations, text extraction alone is insufficient.

For each page: - Store a rendered page image or reproducible
reference. - Identify visual regions and retain page number and bounding
box. - De-duplicate identical image bytes where useful, while preserving
each distinct placement. - Associate figures with captions and nearby
text. - Send selected regions to a vision-capable model when extraction
is incomplete or a description is needed. - Preserve the original
page/crop reference alongside model-generated descriptions.

For charts, retain title, axes, labels, legend, units, and plotted
relationships where visible. For tables, retain headers and cell
relationships. For equations, retain extracted notation and an image
reference for verification.

Vision-generated descriptions are derived metadata, not source truth.
The Tutor must be able to retrieve the original page or crop for visual
questions.

### 5.4 Chunking

Use semantic, page-aware chunks rather than fixed character-only
splitting.

-   Prefer section and paragraph boundaries.
-   Keep headings with the content they introduce.
-   Keep table headers with rows, or store a structured table plus a
    searchable textual representation.
-   Keep figure captions with relevant nearby explanation.
-   Treat equations as distinct content units with surrounding
    explanatory text.
-   Use limited overlap only where needed to preserve context.
-   Do not combine unrelated sections just to fill a token target.

Recommended chunk metadata:

  -----------------------------------------------------------------------
  Field                               Purpose
  ----------------------------------- -----------------------------------
  `chunk_id`                          Stable unique chunk ID

  `document_id`                       Source reading

  `course_code`                       Course association

  `title`                             Reading title

  `page_start`, `page_end`            Original PDF page range

  `section_path`                      Heading hierarchy

  `content_type`                      `text`, `table`, `figure_caption`,
                                      `equation`, `visual_description`

  `text`                              Searchable text

  `asset_ids`                         Related page renders or figure
                                      crops

  `source_version`                    Original PDF version

  `parser_version`                    Extraction pipeline version

  `embedding_model`                   Embedding model identifier

  `quality_status`                    Validation status
  -----------------------------------------------------------------------

Metadata supports filtering by course, reading, page, and content type,
as well as citation generation and retrieval improvements.

### 5.5 Embeddings and indexing

Generate embeddings for searchable text chunks and, where useful,
verified visual descriptions. Store vectors with chunk text and metadata
in PostgreSQL using pgvector.

MVP retrieval should support: - Vector similarity. - Lexical/full-text
search. - Hybrid combination of both. - Course and document metadata
filters. - Configurable result limits. - Source references returned with
every result.

An embedding of a generated image description is not equivalent to the
original visual evidence. Retain and retrieve the original page/crop for
visual questions.

A later production enhancement can add a reranker after initial
retrieval to improve the final evidence set.

### 5.6 PDF quality gates

Do not mark a PDF `READY` merely because parsing completed. Check: -
Page count matches the source. - Expected pages have usable extracted
text or an explicit OCR outcome. - Page numbers and source references
are valid. - Tables retain usable headers and row/column
relationships. - Figures and captions retain page placement. - Displayed
equations are captured or flagged for visual verification. - Duplicate
image payloads do not erase distinct placements. - Chunks have document
and course metadata. - Embeddings exist for chunks eligible for semantic
search. - A sample of extracted content has been checked against
rendered pages.

If an important figure, table, or equation is not reliably recovered,
mark affected content `NEEDS_REVIEW` rather than silently publishing
incomplete evidence.

## 6. JSON academic data pipeline

### 6.1 Schema validation

Validate each JSON file against a versioned schema before loading.

For the course catalogue: - Required top-level fields. - Unique course
codes. - Positive course units. - Valid term names. - Prerequisite
course references. - Material paths and course associations. - Programme
identifiers and requirement definitions. - Supported rules such as `all`
and `choose`. - Required count values for choice requirements.

For student records: - Unique student IDs. - Valid programme
references. - Adviser identifiers. - Completed and enrolled course
references. - Valid term values. - No duplicate entries with conflicting
statuses. - No course simultaneously completed and in progress unless a
documented rule permits it.

### 6.2 Referential integrity

After schema validation, verify: - Every student `program_id` resolves
to a catalogue programme. - Every completed/enrolled `course_code`
exists. - Every prerequisite refers to a known course. - Every material
path maps to an expected source object. - Every programme requirement
references known courses.

Invalid references should fail the load or be quarantined for
correction. Do not silently discard unknown courses or invent missing
rules.

### 6.3 Relational storage

A practical PostgreSQL model:

  -----------------------------------------------------------------------
  Table                               Purpose
  ----------------------------------- -----------------------------------
  `programs`                          Programme IDs and names

  `program_requirements`              Requirement name, rule, required
                                      count

  `requirement_courses`               Courses associated with each
                                      requirement

  `courses`                           Course code, title, units,
                                      description

  `course_prerequisites`              Course-to-prerequisite
                                      relationships

  `course_terms`                      Terms in which a course is offered

  `course_materials`                  Course, reading title, week,
                                      document ID

  `students`                          Student ID, academic level,
                                      programme, adviser

  `student_course_history`            Student, course, term, status

  `adviser_assignments`               Student/adviser relationship

  `ingestion_jobs`                    Job ID, source key, status, error
                                      summary, timestamps
  -----------------------------------------------------------------------

Use foreign keys and unique constraints. Preserve source JSON and
checksums to trace structured records back to the input fixture.

### 6.4 Planning is not vector search

Course recommendation and degree progress must use SQL-backed records
and deterministic Python rules.

The rules engine should: 1. Load completed courses and current
enrolments. 2. Identify the target term. 3. Find courses offered in that
term. 4. Evaluate prerequisites using the supplied policy. 5. Calculate
outstanding degree requirements. 6. Apply the institutional 16-unit
maximum. 7. Apply any lower user-requested cap. 8. Return eligible
courses, exclusions, requirement progress, and reasons.

A Fall 2026 in-progress course may count toward a Spring 2027
prerequisite, but it remains `in_progress` in the academic record. Do
not represent it as completed.

The Academic Planning agent explains structured rule results. The LLM
does not independently decide prerequisite satisfaction.

## 7. Retrieval-time data flow

``` mermaid
flowchart TD
    Q[Student question] --> AUTH[Authorize student and course scope]
    AUTH --> CTX[Resolve course and reading context]
    CTX --> QUERY[Build search query]
    QUERY --> FILTER[Apply course/document metadata filters]
    FILTER --> HYBRID[Hybrid lexical + vector retrieval]
    HYBRID --> RANK[Rank candidate chunks]
    RANK --> EVID[Assemble text, page and asset references]
    EVID --> VIS{Visual evidence needed?}
    VIS -->|No| PROMPT[Build grounded context]
    VIS -->|Yes| ASSET[Fetch page render / figure crop from S3]
    ASSET --> PROMPT
    PROMPT --> LLM[Generate answer from evidence]
    LLM --> CHECK[Validate citations and evidence coverage]
    CHECK -->|Supported| ANSWER[Return answer with citations]
    CHECK -->|Insufficient| LIMIT[State limitation or ask clarification]
```

For follow-ups, conversation state may provide a previously referenced
`document_id`, page, or `asset_id`. Re-check that the user remains
authorized to access the source.

## 8. Versioning, refresh, and idempotency

-   Preserve every original source version.
-   Calculate checksums to detect unchanged files.
-   Use stable document/chunk IDs where practical.
-   Make ingestion idempotent so retries do not create duplicate records
    or chunks.
-   Record parser, embedding model, and schema versions.
-   When a PDF changes, reprocess that document and supersede old
    chunks.
-   When catalogue/student JSON changes, validate the new snapshot
    before publishing it.
-   Track statuses such as `PENDING`, `PROCESSING`, `READY`,
    `NEEDS_REVIEW`, and `FAILED`.
-   Use transactions for structured data updates so partially loaded
    snapshots are not exposed.

For production, consider effective dates and source-system version
identifiers for course and degree rules. Historical rule versioning is
not defined by the sample data and must be confirmed with the
institution.

## 9. Security and governance

-   Keep original PDFs and processed assets in private S3 buckets.
-   Encrypt data at rest and use TLS in transit.
-   Restrict S3 access to ingestion workers and authorized application
    roles.
-   Apply database credentials and network access controls.
-   Enforce student/adviser data scope in the backend, not in prompts.
-   Avoid placing unnecessary student identifiers or sensitive academic
    data in model prompts.
-   Avoid logging full student records or sensitive conversation content
    by default.
-   Treat document text and embedded content as untrusted; PDFs may
    contain prompt-injection instructions.
-   Validate URLs before retrieval; use explicit allowlists and block
    private, loopback, link-local, and cloud metadata destinations.
-   Establish retention/deletion rules with the institution; they are
    not specified in the sample scenario.

## 10. AWS deployment mapping

  -----------------------------------------------------------------------
  Capability              Proposed MVP AWS        Notes
                          component               
  ----------------------- ----------------------- -----------------------
  Original and processed  Amazon S3               Private buckets,
  files                                           encryption, versioning
                                                  as required

  Ingestion queue         Amazon SQS              Decouples upload from
                                                  processing

  PDF/JSON processing     ECS Fargate worker      Separate from
                                                  interactive workload

  UI/API                  ECS Fargate             Lightweight Gradio MVP

  Model inference         Amazon Bedrock          Subject to region,
                                                  model availability, and
                                                  institutional approval

  Structured academic     Amazon RDS for          Relational constraints
  data                    PostgreSQL              and transactions

  Vector retrieval        pgvector in PostgreSQL  Chunk embeddings and
                                                  metadata

  Authentication          Amazon Cognito for MVP  Institutional SSO
                                                  integration to be
                                                  validated

  Secrets                 Secrets Manager or      No credentials in
                          Systems Manager         source control
                          Parameter Store         

  Observability           Amazon CloudWatch       Logs, metrics, alarms

  Infrastructure as code  AWS CDK v2              Repeatable provisioning
  -----------------------------------------------------------------------

This is a proposed mapping, not a claim that the services are already
deployed. Validate quotas, regional availability, data residency,
networking, model access, and institutional security requirements.

## 11. Data acceptance tests

  -----------------------------------------------------------------------
  Test                                Expected result
  ----------------------------------- -----------------------------------
  Catalogue schema                    All 14 courses and programme
                                      requirements validate

  Student schema                      Both student records validate

  Course references                   All completed/enrolled course codes
                                      resolve

  Programme references                Both programme IDs resolve

  Prerequisite references             All prerequisite codes resolve

  PDF preflight                       Page counts and source metadata
                                      recorded for all readings

  Visual extraction                   Figures, charts, tables, and
                                      equations extracted or explicitly
                                      flagged

  Citation traceability               Every chunk resolves to original
                                      document and page

  Hybrid retrieval                    Course-filtered queries return
                                      relevant chunks with metadata

  Re-ingestion                        Same source does not create
                                      duplicates

  Changed source                      New version supersedes affected
                                      derived content

  Access isolation                    Student cannot retrieve another
                                      student's records

  Planning correctness                Eligibility and unit totals match
                                      deterministic rules

  Missing evidence                    Application reports insufficient
                                      evidence rather than fabricating an
                                      answer
  -----------------------------------------------------------------------

## 12. MVP delivery sequence

1.  Register and preserve source files.
2.  Validate catalogue and student JSON schemas and cross-references.
3.  Build the PDF extraction pipeline and test it on one representative
    reading.
4.  Add visual enrichment, page-aware chunking, metadata, and
    embeddings.
5.  Process the remaining readings through the same pipeline.
6.  Implement hybrid retrieval and citation traceability.
7.  Implement relational academic storage and deterministic planning
    rules.
8.  Integrate Tutor and Planner with the LangGraph Supervisor.
9.  Test the four sample conversations, including follow-ups.
10. Deploy the Gradio application and ingestion worker to AWS using CDK
    v2.

The MVP is ready for demonstration when the datasets can be ingested
reproducibly, tutoring answers are traceable to readings, planning
calculations are deterministic, and access controls are enforced.
