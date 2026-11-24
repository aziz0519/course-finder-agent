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

<div style="width:100%; overflow-x:auto;">

<svg style="width:100%; min-width:960px; display:block;" viewBox="0 0 960 600" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="cfa-overview-title cfa-overview-desc">
        <title id="cfa-overview-title">UI and backend runtime overview</title>
        <desc id="cfa-overview-desc">A Gradio UI sends authenticated requests to a FastAPI backend, where policy gates delegate to agents and deterministic rules before reading local stores; an on-demand worker ingests fixture files into those stores.</desc>
        <defs>
          <marker id="cfa-overview-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#4f5d75"/></marker>
          <marker id="cfa-overview-arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#bf4520"/></marker>
          <marker id="cfa-overview-arrow-link" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#2e5aa8"/></marker>
        </defs>

        <rect width="100%" height="100%" fill="#f5f5f5"/>

        <!-- Zones -->
        <rect x="40" y="80" width="192" height="420" rx="8" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <rect x="48" y="84" width="64" height="12" rx="2" fill="#f5f5f5"/>
        <text x="52" y="93" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">CLIENT</text>

        <rect x="256" y="80" width="400" height="420" rx="8" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <rect x="264" y="84" width="136" height="12" rx="2" fill="#f5f5f5"/>
        <text x="268" y="93" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">BACKEND - FASTAPI</text>

        <rect x="680" y="80" width="240" height="420" rx="8" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <rect x="688" y="84" width="96" height="12" rx="2" fill="#f5f5f5"/>
        <text x="692" y="93" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">DATA &amp; JOBS</text>

        <!-- Arrows first, drawn behind nodes -->
        <line x1="136" y1="200" x2="136" y2="280" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="144" y="228" width="56" height="12" rx="2" fill="#f5f5f5"/>
        <text x="172" y="237" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">REQUEST</text>

        <path d="M216,312 H240 Q248,312 248,304 V176 Q248,168 256,168 H280" fill="none" stroke="#2e5aa8" stroke-width="1.2" marker-end="url(#cfa-overview-arrow-link)"/>
        <rect x="258" y="228" width="64" height="12" rx="2" fill="#f5f5f5"/>
        <text x="290" y="237" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">HTTP+CSRF</text>

        <line x1="432" y1="168" x2="480" y2="168" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="436" y="148" width="40" height="12" rx="2" fill="#f5f5f5"/>
        <text x="456" y="157" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">SCOPE</text>

        <line x1="356" y1="200" x2="356" y2="280" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="366" y="228" width="40" height="12" rx="2" fill="#f5f5f5"/>
        <text x="386" y="237" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">RULES</text>

        <line x1="556" y1="200" x2="556" y2="280" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="566" y="228" width="40" height="12" rx="2" fill="#f5f5f5"/>
        <text x="586" y="237" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">TOOLS</text>

        <line x1="432" y1="312" x2="480" y2="312" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="436" y="292" width="40" height="12" rx="2" fill="#f5f5f5"/>
        <text x="456" y="301" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">RESULT</text>

        <path d="M632,312 H656 Q664,312 664,320 V424 Q664,432 672,432 H700" fill="none" stroke="#4f5d75" stroke-width="1" stroke-dasharray="5,4" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="674" y="360" width="64" height="12" rx="2" fill="#f5f5f5"/>
        <text x="706" y="369" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">RETRIEVE</text>

        <line x1="800" y1="200" x2="800" y2="280" stroke="#4f5d75" stroke-width="1" stroke-dasharray="5,4" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="810" y="228" width="64" height="12" rx="2" fill="#f5f5f5"/>
        <text x="842" y="237" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">JSON+PDF</text>

        <line x1="800" y1="344" x2="800" y2="400" stroke="#4f5d75" stroke-width="1" stroke-dasharray="5,4" marker-end="url(#cfa-overview-arrow)"/>
        <rect x="810" y="356" width="64" height="12" rx="2" fill="#f5f5f5"/>
        <text x="842" y="365" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">PUBLISH</text>

        <!-- Nodes -->
        <g>
          <rect x="56" y="136" width="160" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="56" y="136" width="160" height="64" rx="6" fill="rgba(79,93,117,0.10)" stroke="#5a6580" stroke-width="1"/>
          <rect x="64" y="142" width="28" height="12" rx="2" fill="transparent" stroke="rgba(90,101,128,0.40)" stroke-width="0.8"/>
          <text x="78" y="151" fill="rgba(90,101,128,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">USER</text>
          <text x="136" y="170" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Students &amp; staff</text>
          <text x="136" y="186" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">3 user roles</text>
        </g>
        <g>
          <rect x="56" y="280" width="160" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="56" y="280" width="160" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="64" y="286" width="28" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="78" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">UI</text>
          <text x="136" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Gradio UI</text>
          <text x="136" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">ui/app.py</text>
        </g>
        <g>
          <rect x="280" y="136" width="152" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="280" y="136" width="152" height="64" rx="6" fill="rgba(191,69,32,0.08)" stroke="#bf4520" stroke-width="1"/>
          <rect x="288" y="142" width="28" height="12" rx="2" fill="transparent" stroke="rgba(191,69,32,0.40)" stroke-width="0.8"/>
          <text x="302" y="151" fill="rgba(191,69,32,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">API</text>
          <text x="356" y="170" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">FastAPI routes</text>
          <text x="356" y="186" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">/api/v1</text>
        </g>
        <g>
          <rect x="480" y="136" width="152" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="480" y="136" width="152" height="64" rx="6" fill="rgba(191,69,32,0.05)" stroke="rgba(191,69,32,0.50)" stroke-width="1" stroke-dasharray="4,4"/>
          <rect x="488" y="142" width="40" height="12" rx="2" fill="transparent" stroke="rgba(191,69,32,0.40)" stroke-width="0.8"/>
          <text x="508" y="151" fill="rgba(191,69,32,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">AUTH</text>
          <text x="556" y="170" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Auth + policy</text>
          <text x="556" y="186" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">session - RBAC</text>
        </g>
        <g>
          <rect x="280" y="280" width="152" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="280" y="280" width="152" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="288" y="286" width="40" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="308" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">DOMAIN</text>
          <text x="356" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Domain rules</text>
          <text x="356" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">eligibility - audit</text>
        </g>
        <g>
          <rect x="480" y="280" width="152" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="480" y="280" width="152" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="488" y="286" width="36" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="506" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">AGENT</text>
          <text x="556" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Supervisor + agents</text>
          <text x="556" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">3 specialists</text>
        </g>
        <g>
          <rect x="700" y="136" width="200" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="700" y="136" width="200" height="64" rx="6" fill="rgba(79,93,117,0.10)" stroke="#5a6580" stroke-width="1"/>
          <rect x="708" y="142" width="40" height="12" rx="2" fill="transparent" stroke="rgba(90,101,128,0.40)" stroke-width="0.8"/>
          <text x="728" y="151" fill="rgba(90,101,128,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">SOURCE</text>
          <text x="800" y="170" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Source fixtures</text>
          <text x="800" y="186" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">catalogue - PDFs</text>
        </g>
        <g>
          <rect x="700" y="280" width="200" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="700" y="280" width="200" height="64" rx="6" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.20)" stroke-width="1" stroke-dasharray="4,3"/>
          <rect x="708" y="286" width="28" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.20)" stroke-width="0.8"/>
          <text x="722" y="295" fill="rgba(45,49,66,0.60)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">JOB</text>
          <text x="800" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Ingestion worker</text>
          <text x="800" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">on-demand container</text>
        </g>
        <g>
          <rect x="700" y="400" width="200" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="700" y="400" width="200" height="64" rx="6" fill="rgba(45,49,66,0.05)" stroke="#4f5d75" stroke-width="1"/>
          <rect x="708" y="406" width="28" height="12" rx="2" fill="transparent" stroke="rgba(79,93,117,0.40)" stroke-width="0.8"/>
          <text x="722" y="415" fill="rgba(79,93,117,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">DATA</text>
          <text x="800" y="434" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Local stores</text>
          <text x="800" y="450" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">SQLite - artefacts</text>
        </g>

        <!-- Legend -->
        <line x1="40" y1="540" x2="920" y2="540" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <line x1="40" y1="560" x2="64" y2="560" stroke="#2e5aa8" stroke-width="1.2"/>
        <text x="72" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">HTTP CALL</text>
        <line x1="208" y1="560" x2="232" y2="560" stroke="#4f5d75" stroke-width="1"/>
        <text x="240" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">INTERNAL CALL</text>
        <line x1="400" y1="560" x2="424" y2="560" stroke="#4f5d75" stroke-width="1" stroke-dasharray="5,4"/>
        <text x="432" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">ON-DEMAND JOB</text>
        <rect x="608" y="556" width="8" height="8" rx="2" fill="rgba(191,69,32,0.08)" stroke="#bf4520" stroke-width="1"/>
        <text x="624" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">FOCAL SERVICE</text>
        <rect x="800" y="556" width="8" height="8" rx="2" fill="rgba(45,49,66,0.05)" stroke="#4f5d75" stroke-width="1"/>
        <text x="816" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">DATA STORE</text>
      </svg>

</div>

The UI is a Gradio app, not Next.js. It keeps only a session cookie and a CSRF token, then calls the `/api/v1` surface over HTTP.
FastAPI authenticates the session, derives the authorized student scope, and passes that scope into the agent layer.
The supervisor delegates to three specialists, with the tutor using scoped retrieval, the planner using deterministic rules, and the context agent reading only the authorized student record.
The on-demand worker ingests the supplied JSON and PDF fixtures into local SQLite and versioned artefacts.

### Backend detail

<div style="width:100%; overflow-x:auto;">

<svg style="width:100%; min-width:960px; display:block;" viewBox="0 0 960 600" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="cfa-backend-title cfa-backend-desc">
        <title id="cfa-backend-title">Backend internals: authorized request path</title>
        <desc id="cfa-backend-desc">The API gate derives an authorized scope for the conversation service, the supervisor delegates to three specialists, and only the tutor reads course evidence while the planner calls deterministic degree and eligibility rules.</desc>
        <defs>
          <marker id="cfa-backend-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#4f5d75"/></marker>
          <marker id="cfa-backend-arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#bf4520"/></marker>
          <marker id="cfa-backend-arrow-link" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#2e5aa8"/></marker>
        </defs>

        <rect width="100%" height="100%" fill="#f5f5f5"/>

        <!-- Zones -->
        <rect x="40" y="80" width="224" height="420" rx="8" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <rect x="48" y="84" width="112" height="12" rx="2" fill="#f5f5f5"/>
        <text x="52" y="93" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">API &amp; THREAD</text>

        <rect x="288" y="80" width="384" height="420" rx="8" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <rect x="296" y="84" width="120" height="12" rx="2" fill="#f5f5f5"/>
        <text x="300" y="93" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">ORCHESTRATION</text>

        <rect x="680" y="80" width="240" height="420" rx="8" fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <rect x="688" y="84" width="112" height="12" rx="2" fill="#f5f5f5"/>
        <text x="692" y="93" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">RULES &amp; DATA</text>

        <!-- Arrows first, drawn behind nodes -->
        <line x1="152" y1="200" x2="152" y2="280" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-backend-arrow)"/>
        <rect x="162" y="228" width="48" height="12" rx="2" fill="#f5f5f5"/>
        <text x="186" y="237" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">SCOPE</text>

        <path d="M248,312 H264 Q272,312 272,304 V176 Q272,168 280,168 H400" fill="none" stroke="#4f5d75" stroke-width="1.2" marker-end="url(#cfa-backend-arrow)"/>
        <rect x="282" y="228" width="64" height="12" rx="2" fill="#f5f5f5"/>
        <text x="314" y="237" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">TURN+STATE</text>

        <path d="M424,200 V232 Q424,240 416,240 H368 Q360,240 360,248 V280" fill="none" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-backend-arrow)"/>
        <line x1="480" y1="200" x2="480" y2="280" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-backend-arrow)"/>
        <path d="M536,200 V232 Q536,240 544,240 H592 Q600,240 600,248 V280" fill="none" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-backend-arrow)"/>

        <path d="M512,280 V224 Q512,216 520,216 H680 Q688,216 688,208 V176 Q688,168 696,168" fill="none" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-backend-arrow)"/>
        <rect x="588" y="196" width="48" height="12" rx="2" fill="#f5f5f5"/>
        <text x="612" y="205" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">CHECK</text>

        <line x1="648" y1="312" x2="696" y2="312" stroke="#4f5d75" stroke-width="1" marker-end="url(#cfa-backend-arrow)"/>
        <rect x="652" y="292" width="40" height="12" rx="2" fill="#f5f5f5"/>
        <text x="672" y="301" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">QUERY</text>

        <path d="M360,344 V368 Q360,376 368,376 H748 Q756,376 756,384 V400" fill="none" stroke="#4f5d75" stroke-width="1" stroke-dasharray="5,4" marker-end="url(#cfa-backend-arrow)"/>
        <rect x="520" y="356" width="96" height="12" rx="2" fill="#f5f5f5"/>
        <text x="568" y="365" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">STUDENT DATA</text>

        <line x1="796" y1="344" x2="796" y2="400" stroke="#4f5d75" stroke-width="1" stroke-dasharray="5,4" marker-end="url(#cfa-backend-arrow)"/>
        <rect x="806" y="356" width="72" height="12" rx="2" fill="#f5f5f5"/>
        <text x="842" y="365" fill="#5a6580" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.06em">EVIDENCE</text>

        <!-- Nodes -->
        <g>
          <rect x="56" y="136" width="192" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="56" y="136" width="192" height="64" rx="6" fill="rgba(191,69,32,0.05)" stroke="rgba(191,69,32,0.50)" stroke-width="1" stroke-dasharray="4,4"/>
          <rect x="64" y="142" width="40" height="12" rx="2" fill="transparent" stroke="rgba(191,69,32,0.40)" stroke-width="0.8"/>
          <text x="84" y="151" fill="rgba(191,69,32,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">GATE</text>
          <text x="152" y="170" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">API gate</text>
          <text x="152" y="186" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">routes - auth - RBAC</text>
        </g>
        <g>
          <rect x="56" y="280" width="192" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="56" y="280" width="192" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="64" y="286" width="40" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="84" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">STATE</text>
          <text x="152" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Conversation service</text>
          <text x="152" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">thread - preferences</text>
        </g>
        <g>
          <rect x="400" y="136" width="160" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="400" y="136" width="160" height="64" rx="6" fill="rgba(191,69,32,0.08)" stroke="#bf4520" stroke-width="1"/>
          <rect x="408" y="142" width="40" height="12" rx="2" fill="transparent" stroke="rgba(191,69,32,0.40)" stroke-width="0.8"/>
          <text x="428" y="151" fill="rgba(191,69,32,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">SUPER</text>
          <text x="480" y="170" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Supervisor</text>
          <text x="480" y="186" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">bounded routing</text>
        </g>
        <g>
          <rect x="312" y="280" width="96" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="312" y="280" width="96" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="320" y="286" width="28" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="334" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">CTX</text>
          <text x="360" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Context</text>
          <text x="360" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">student scope</text>
        </g>
        <g>
          <rect x="432" y="280" width="96" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="432" y="280" width="96" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="440" y="286" width="28" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="454" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">PLAN</text>
          <text x="480" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Planner</text>
          <text x="480" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">degree - plan</text>
        </g>
        <g>
          <rect x="552" y="280" width="96" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="552" y="280" width="96" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="560" y="286" width="36" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="578" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">TUTOR</text>
          <text x="600" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Tutor</text>
          <text x="600" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">readings</text>
        </g>
        <g>
          <rect x="696" y="136" width="200" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="696" y="136" width="200" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="704" y="142" width="40" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="724" y="151" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">RULES</text>
          <text x="796" y="170" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Deterministic rules</text>
          <text x="796" y="186" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">eligibility - audit</text>
        </g>
        <g>
          <rect x="696" y="280" width="200" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="696" y="280" width="200" height="64" rx="6" fill="#ffffff" stroke="#2d3142" stroke-width="1"/>
          <rect x="704" y="286" width="28" height="12" rx="2" fill="transparent" stroke="rgba(45,49,66,0.40)" stroke-width="0.8"/>
          <text x="718" y="295" fill="rgba(45,49,66,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">RETR</text>
          <text x="796" y="314" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Course retrieval</text>
          <text x="796" y="330" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">course - page - asset</text>
        </g>
        <g>
          <rect x="696" y="400" width="200" height="64" rx="6" fill="#f5f5f5"/>
          <rect x="696" y="400" width="200" height="64" rx="6" fill="rgba(45,49,66,0.05)" stroke="#4f5d75" stroke-width="1"/>
          <rect x="704" y="406" width="28" height="12" rx="2" fill="transparent" stroke="rgba(79,93,117,0.40)" stroke-width="0.8"/>
          <text x="718" y="415" fill="rgba(79,93,117,0.80)" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle" letter-spacing="0.08em">DATA</text>
          <text x="796" y="434" fill="#2d3142" font-size="12" font-weight="600" font-family="'Geist', system-ui, sans-serif" text-anchor="middle">Authorized stores</text>
          <text x="796" y="450" fill="#4f5d75" font-size="9" font-family="'Geist Mono', ui-monospace, monospace" text-anchor="middle">SQLite - artefacts</text>
        </g>

        <!-- Legend -->
        <line x1="40" y1="540" x2="920" y2="540" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
        <line x1="40" y1="560" x2="64" y2="560" stroke="#4f5d75" stroke-width="1"/>
        <text x="72" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">TYPED CALL</text>
        <line x1="240" y1="560" x2="264" y2="560" stroke="#4f5d75" stroke-width="1" stroke-dasharray="5,4"/>
        <text x="272" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">READ ONLY</text>
        <rect x="440" y="556" width="8" height="8" rx="2" fill="rgba(191,69,32,0.08)" stroke="#bf4520" stroke-width="1"/>
        <text x="456" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">DECISION POINT</text>
        <rect x="656" y="556" width="8" height="8" rx="2" fill="rgba(45,49,66,0.05)" stroke="#4f5d75" stroke-width="1"/>
        <text x="672" y="564" fill="#4f5d75" font-size="8" font-family="'Geist Mono', ui-monospace, monospace" letter-spacing="0.14em">DATA STORE</text>
      </svg>

</div>


Authorization runs before any agent tool executes.
The conversation service owns thread state and the user's unit-cap preference, but authoritative academic data is re-read on every turn.
The tutor is the only component that reads reading chunks and figure assets, and those reads are filtered by course and document scope.
The planner calls the deterministic eligibility and degree-rule engine; a model may explain those results but may not change them.

Editable diagram sources: [architecture-overview.html](./docs/diagrams/architecture-overview.html) and [backend-internals.html](./docs/diagrams/backend-internals.html).
GitHub's Markdown sanitizer may hide inline SVG; open the HTML files directly in that case.

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