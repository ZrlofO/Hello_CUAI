# HICAREER LangGraph Multi-Agent Career Consulting Master Plan

> Repository-aware implementation plan. This document defines the target architecture and implementation sequence; it does not itself implement the product.

## 1. Executive Summary

HICAREER analyzes a PDF CV, preferred career role, and preparation period. It normalizes the CV into provenance-aware metadata, pauses for user review, researches current hiring evidence, conservatively selects improvement areas, activates only relevant Supporting Agents, verifies atomic claims through a reusable LLM Judge and web evidence, classifies readiness risk, generates a realistic preparation plan, and renders a traceable final report.

Factual credibility is the primary product constraint. Fluent or repeated LLM output is never evidence. Every important external claim, job requirement, active status, deadline, accepted-candidate case, credential, recommendation, or schedule must reference an Evidence Ledger record and a claim-level verification status.

The repository is currently a small vanilla web application:

- Frontend: static HTML, vanilla JavaScript, and CSS.
- Backend: Python http.server and ThreadingHTTPServer.
- Existing APIs: /api/jobs/popular, /api/extract-cv, and /api/analyze-cv.
- Existing integrations: OpenAI Responses API, Work24 API, and Saramin/JobKorea scraping.
- Persistence: browser sessionStorage/localStorage only.
- LangGraph: not installed.
- Pydantic: available in the current environment.

The implementation must extend the existing application rather than create a disconnected replacement. server.py should gradually become a compatibility layer over modular graph, agent, retrieval, evidence, and API services.

## 2. Product Goals

- Support PDF-only CV upload as the primary input.
- Normalize different CV layouts, languages, and detail levels into one schema.
- Preserve raw PDF/text traceability while making confirmed metadata the downstream source of truth.
- Let users review, correct, delete, add, and confirm metadata without editing JSON.
- Retrieve current information from configurable internet sources without requiring persistent RAG initially.
- Use deterministic code for validation, scoring, thresholds, freshness, routing, retries, and policy enforcement.
- Use LLMs for semantic extraction, research interpretation, recommendations, and claim verification.
- Run only relevant Supporting Agents and isolate partial branch failures.
- Produce evidence-backed recommendations, timeline items, Todo tasks, citations, warnings, and uncertainty notes.
- Never imply guaranteed employment or acceptance.

## 3. Non-Goals

- Employment or interview guarantees.
- Treating plausible model output or agent agreement as evidence.
- Building a persistent RAG database in the first release.
- Rebuilding the frontend unnecessarily.
- Fully implementing the future always-running Grammar Agent initially.
- Preserving demo behavior when it conflicts with this workflow.
- Adding unrelated features during this migration.

## 4. Repository Assessment

| Path | Current purpose | Planned disposition |
|---|---|---|
| index.html | Landing page and popular jobs | Reuse and extend |
| diagnosis.html | CV input and analysis entry | Modify for workflow and metadata review |
| report.html | Static sample report | Replace with API-driven rendering |
| opportunities.html | Static activity recommendations | Modify for verified recommendations |
| plan.html | Static growth plan | Modify for Planner output |
| script.js | Upload, extraction, analysis UI | Refactor into workflow client |
| jobs.js | Job search, caching, filtering, cards | Reuse with evidence/status fields |
| styles.css | Shared visual system | Reuse and extend |
| server.py | HTTP server, scraping, ranking, LLM calls | Decompose behind compatible routes |
| README.md | MVP documentation | Update to new architecture |
| .env.example | Work24/OpenAI configuration | Extend with graph and retrieval configuration |
| requirements.txt | Currently no substantive packages | Pin compatible dependencies |

The repository contains Korean strings that appear to have encoding/mojibake issues. Phase 0 must verify file encoding and browser rendering before changing product copy. This is a repository-specific risk and must not be confused with the LangGraph migration.

## 5. Existing UI Assessment

### Reusable without major redesign

- Existing navigation and page layout.
- diagnosis.html upload card and role input pattern.
- Existing job cards, filters, loading skeletons, and responsive CSS.
- index.html job discovery section.
- Shared styles, buttons, cards, grids, and status patterns.

### Reusable with modification

- diagnosis.html: replace the current PDF/manual branching with PDF upload, preferred role, preparation period, metadata review, additional information, and confirmation.
- script.js: replace the single synchronous analysis call with workflow creation, status polling, metadata mutations, interrupt resume, and final report rendering.
- report.html: consume the final report contract instead of static sample data.
- opportunities.html and plan.html: display evidence status, date type, warnings, and confirmation state.

### Replace or deprecate

- Manual CV mode as a primary input path; retain it only as additional information.
- Free-form PDF bullet mapping as the canonical metadata model.
- Single safe_llm_report generation as the final source of truth.
- Sample jobs presented without an explicit demo/fallback label.
- Simple keyword/cosine ranking as the final readiness or recommendation decision.

## 6. Existing API Demo Assessment

Current routes:

- GET /api/jobs/popular?limit=&keyword=: Work24/Saramin/JobKorea retrieval with fallback jobs.
- POST /api/extract-cv: multipart PDF sent to OpenAI file input and mapped to editable fields.
- POST /api/analyze-cv: multipart or JSON CV input, ranking, agent-like summaries, and optional LLM report.

Reusable patterns:

- Existing multipart parsing.
- Environment-variable configuration.
- Job normalization and cache TTL.
- Static-file serving.
- Existing response JSON conventions.

Migration requirements:

- Keep old routes temporarily as compatibility adapters.
- Add workflow routes for long-running graph execution.
- Label fallback data as DEMO_DATA or FALLBACK, never verified evidence.
- Move model calls, scraping, ranking, and response assembly out of the HTTP handler.

## 7. End-to-End Workflow

    POST /api/workflows
      -> validate PDF, role, preparation period
      -> extract text and page/source spans
      -> normalize metadata
      -> persist checkpoint
      -> interrupt for metadata review

    PATCH /api/workflows/{id}/metadata/items/{item_id}
    DELETE /api/workflows/{id}/metadata/items/{item_id}
    POST /api/workflows/{id}/metadata/items
    POST /api/workflows/{id}/metadata/confirm
      -> apply revision-checked user edits

    POST /api/workflows/{id}/resume
      -> Leading initialization
      -> Consulting research
      -> deterministic company selection
      -> market requirements and reference cases
      -> conservative gap selection
      -> relevant Supporting Agents in parallel
      -> Consulting review
      -> Judge verification and bounded debate
      -> readiness classification
      -> Planner and Todo generation
      -> optional calendar approval interrupt
      -> final report assembly and validation

The workflow must not run as one synchronous HTTP request.

## 8. LangGraph Architecture

Use one parent graph with parallel Supporting Agent branches and reusable verification subgraphs.

### Parent nodes

1. validate_request
2. extract_pdf_text
3. normalize_metadata
4. metadata_review_interrupt
5. initialize_leading_agent
6. consulting_research
7. select_companies
8. extract_market_requirements
9. select_gaps
10. activate_supporting_agents
11. supporting_agents_parallel
12. consulting_review
13. judge_claims
14. adaptive_router
15. classify_readiness
16. planner_agent
17. calendar_confirmation_interrupt
18. assemble_final_report
19. final_schema_validation
20. complete or partial_completion

### State categories

Persistent state: confirmed metadata, claims, evidence ledger, approved outputs, final report, audit history.

Request-scoped state: PDF reference, extraction text, current workflow status, user input.

Temporary state: raw search responses, intermediate passages, candidate claims, provider-specific payloads.

UI-facing state: workflow status, progress events, review data, report sections, warnings, and errors.

### Typed state

Use Pydantic domain models serialized into LangGraph state. Required state fields include:

    request_id
    workflow_status
    user_input
    pdf_metadata
    raw_extracted_text
    text_spans
    raw_extraction_result
    normalized_metadata
    user_confirmed_metadata
    metadata_revision
    selected_companies
    market_requirements
    reference_cases
    claims
    evidence_ledger
    identified_gaps
    activated_agents
    supporting_outputs
    consulting_reviews
    judge_results
    confidence_summary
    retry_counters
    debate_history
    readiness_classification
    recommendations
    planner_result
    calendar_proposals
    todo_items
    final_report
    errors
    warnings
    timestamps

Raw PDF bytes and full CV text should not be copied into durable state unnecessarily. Store secure references and redact sensitive content from logs.

## 9. Graph Edges and Conditional Routing

Deterministic routes:

- Invalid request -> request error.
- Extraction failure -> bounded extraction retry, then actionable error.
- Metadata schema failure -> one repair attempt, then review/error.
- Unconfirmed metadata -> interrupt.
- Missing evidence -> retrieval.
- Incomplete Supporting output -> only the relevant Supporting Agent.
- Contradiction -> contradiction search and Judge.
- Low confidence -> revision or escalation.
- Approved claims and outputs -> next stage.
- Retry/debate limit exceeded -> UNVERIFIABLE or partial completion.
- Unknown claim during final synthesis -> reject and reassemble.

An LLM may suggest a next action, but policy code enforces the actual route.

## 10. Human-in-the-Loop Flow

1. User uploads PDF and enters role and preparation period.
2. Backend validates and extracts the PDF.
3. Graph normalizes metadata and pauses.
4. UI renders editable category cards.
5. User corrects, removes, or adds items.
6. Backend applies revision-checked mutations.
7. User confirms the profile.
8. Graph resumes using only user_confirmed_metadata.
9. Planner creates calendar proposals.
10. User optionally approves calendar writes.

MVP persistence: LangGraph checkpointing with SQLite and workflow IDs. Production extension: PostgreSQL checkpointing, object storage, background workers, resumable execution, and event streaming.

## 11. Metadata Normalization Purpose

Metadata extraction is a canonicalization boundary, not merely summarization. Downstream agents should consume confirmed normalized metadata instead of independently reinterpreting the raw PDF.

The metadata layer must:

- preserve original meaning;
- distinguish missing data from negative evidence;
- retain page and source references;
- support user corrections and additions;
- preserve inferred values as unconfirmed;
- expose extraction confidence and warnings; and
- provide one stable input representation for all agents.

### Canonical stages

1. RawExtraction
2. NormalizedMetadata
3. UserConfirmedMetadata

Only UserConfirmedMetadata is authoritative for analysis.

## 12. Metadata Schema

Each metadata item contains:

    item_id
    category
    sub_category
    normalized_value
    original_text
    source_page
    source_location
    provenance
    extraction_confidence
    verification_status
    user_confirmation_status
    created_at
    updated_at

Product-facing categories:

- Activities and career experience.
- Awards.
- Leadership-related experience.
- Volunteering and contribution.
- Language proficiency.
- Certifications and credentials.
- Preference information.

Internal subcategories include projects, internships, research, competitions, professional work, teamwork, mentoring, community activity, coursework, tools, frameworks, quantified results, and education.

## 13. Metadata Provenance Model

Allowed provenance values:

    CV_EXTRACTED
    USER_PROVIDED
    USER_CORRECTED
    INFERRED
    MISSING
    CONFLICTING

INFERRED never counts as confirmed evidence. MISSING means unavailable information, not proof of absence. CONFLICTING requires explicit review and cannot silently resolve itself.

## 14. Metadata Review UI and API

Required operations:

- GET /api/workflows/{id}
- GET /api/workflows/{id}/events
- PATCH /api/workflows/{id}/metadata/items/{item_id}
- DELETE /api/workflows/{id}/metadata/items/{item_id}
- POST /api/workflows/{id}/metadata/items
- POST /api/workflows/{id}/metadata/confirm
- POST /api/workflows/{id}/resume

Every mutation includes base_revision. Conflicts return a reviewable conflict response rather than overwriting data. Confirmed items cannot be silently changed by agents.

The UI uses cards, structured forms, and editable lists. Raw JSON editing is not required.

## 15. Leading Agent Responsibilities

The Leading Agent:

- starts metadata extraction;
- receives confirmed metadata;
- maintains high-level workflow state;
- invokes Consulting;
- coordinates gap selection and approval;
- forwards approved recommendations to Planner;
- assembles the final report; and
- references only approved claims and graph state.

It must not invent external facts or reinterpret rejected evidence.

## 16. Consulting Agent Responsibilities

The Consulting Agent uses a configurable source registry to:

- identify up to 10 relevant companies with active opportunities;
- retrieve up to 20 credible reference cases when available;
- distinguish common requirements from company-specific preferences;
- compare market requirements with confirmed metadata;
- select evidence-backed improvement categories;
- review Supporting Agent outputs; and
- produce readiness classification inputs.

Counts are configurable upper limits, not mandatory counts. Fewer valid sources must result in fewer results, never invented entries.

Company selection must use inspectable factors: role relevance, active status, experience match, skill match, location constraints, source quality, and freshness.

## 17. Supporting Agent Responsibilities

Supporting Agents run only for selected gaps and receive relevant confirmed metadata, approved evidence, gap reasoning, and assigned scope.

### Project and Career Experience Agent

Projects, external activities, internships, research, competitions, professional experience, practical experience, and measurable results.

### Leadership and Contribution Agent

Leadership, teamwork, organizational experience, volunteering, mentoring, and community activity.

### Language and Credential Agent

Language proficiency, certifications, completion certificates, education, training, tools, and formal qualifications.

### CV Positioning and Expression Agent

CV structure, target-role fit, wording, quantified impact, ATS compatibility, consistency, and evidence-supported positioning.

Each output must reference metadata item IDs, claim IDs, and evidence IDs. It must distinguish missing evidence from confirmed absence and never fabricate user experience, programs, qualifications, URLs, or expected outcomes.

## 18. Consulting Review Loop

After each Supporting Agent returns:

1. Consulting evaluates grounding, relevance, feasibility, currentness, and scope.
2. The result receives one review status.
3. Deterministic routing enforces the status.

Allowed statuses:

    APPROVED
    REVISION_REQUIRED
    MORE_EVIDENCE_REQUIRED
    OUT_OF_SCOPE
    UNVERIFIABLE
    ESCALATE_TO_JUDGE

REVISION_REQUIRED reruns only the relevant Supporting Agent. The graph never restarts all agents unnecessarily.

## 19. LLM Judge Responsibilities

The Judge is a reusable claim-level verification layer invoked after retrieval, Consulting research, Supporting output, recommendation generation, Planner output, and final synthesis when required.

It optimizes for factual support, traceability, contradiction detection, uncertainty preservation, source quality, and freshness. It must not optimize for completeness or helpfulness.

Allowed verdicts:

    SUPPORTED
    PARTIALLY_SUPPORTED
    CONTRADICTED
    UNVERIFIABLE
    AMBIGUOUS
    STALE_EVIDENCE
    SOURCE_QUALITY_INSUFFICIENT

Required fields:

    claim_id
    evidence_ids
    contradicting_evidence_ids
    evidence_status
    source_quality
    freshness
    confidence
    verdict
    required_next_action
    reason

No hidden chain-of-thought is required or stored.

## 20. Shared Anti-Hallucination Instruction

Every agent receives a versioned global instruction:

1. Use only confirmed metadata, approved graph state, tool outputs, and verified evidence.
2. Never fabricate user facts, URLs, dates, companies, programs, credentials, statistics, or hiring outcomes.
3. Separate facts, inferences, recommendations, and uncertainties.
4. Attach claim-level provenance.
5. Prefer conservative conclusions.
6. Report unavailable evidence honestly.
7. Reject stale, expired, inaccessible, or invalid information when current validity matters.
8. Use only the latest approved graph state.
9. Do not reuse rejected evidence without re-verification.
10. Follow structured output schemas.
11. Do not introduce factual claims during summarization.
12. Do not treat agent agreement as independent evidence.
13. Do not silently alter user-confirmed metadata.
14. Never promise employment or acceptance.
15. Make wording proportional to evidence strength.

## 21. Claim Model

Each atomic claim contains:

    claim_id
    claim_text
    claim_type
    subject
    predicate
    object_or_value
    produced_by
    metadata_refs
    evidence_ids
    importance
    external_verification_required
    current_verdict
    confidence
    review_history

Claim types include user fact, extracted CV fact, corrected fact, market fact, job-posting fact, deadline fact, accepted-candidate case, inference, gap assessment, recommendation, scheduling fact, and final-report statement.

## 22. Evidence Ledger

Each evidence record contains:

    evidence_id
    claim_id
    source_type
    source_url
    source_title
    publisher
    publication_date
    retrieval_date
    application_deadline
    active_status
    relevant_excerpt
    normalized_fact
    source_quality_score
    freshness_score
    relevance_score
    support_status
    retrieval_query
    retrieved_by_node
    verification_status
    rejection_reason

Agents pass claim IDs and evidence IDs instead of repeating long unstructured summaries. High-impact claims cannot be approved without evidence.

## 23. Web Retrieval Pipeline

1. Search-intent generation.
2. Claim and entity extraction.
3. Query generation.
4. Query diversification.
5. Web search.
6. Result deduplication.
7. Source-quality filtering.
8. Original-page retrieval.
9. Relevant-passage extraction.
10. Publication-date extraction.
11. Deadline and active-status verification.
12. Contradiction search.
13. Evidence normalization.
14. Judge verification.
15. Evidence Ledger storage.

The source registry defines domains, authority, allowed claim types, freshness windows, parsers, and rate limits. Search snippets are discovery aids only when original pages are accessible.

## 24. Source-Quality Policy

Source priority:

1. Official company recruitment page.
2. Official institution or education-provider page.
3. Attributable first-person account or interview.
4. Reputable secondary summary.
5. Anonymous community anecdote.

Anonymous or low-authority material may be retained only as explicitly labeled qualitative context. It must not be used as strong ground truth.

## 25. Freshness and Expiration Policy

- Active jobs and deadlines must be revalidated at request time.
- Current requirements use configurable freshness windows.
- Historical cases require publication dates and historical labels.
- Missing dates reduce freshness confidence.
- Expired opportunities are excluded from active recommendations and calendar writes.
- Conflicting dates become AMBIGUOUS until resolved.
- An unavailable original page cannot support a high-impact current claim by itself.

## 26. Relevant Company Selection

Use a deterministic or hybrid score with inspectable components:

    role_relevance
    active_status
    experience_level_match
    skill_match
    location_match
    evidence_quality
    freshness

The score produces a ranked shortlist, but a hard policy filter first removes inactive, inaccessible, or insufficiently evidenced postings. Semantic ranking may refine the shortlist but may not bypass policy filters.

## 27. Accepted-Candidate and Reference-Case Policy

Every reference case must record source type and explicit acceptance support.

Allowed labels:

- official company-published case;
- official institution-published case;
- verified first-person account;
- attributable interview;
- secondary summary;
- anonymous community anecdote;
- unverified claim.

The system must not state that a candidate was accepted unless evidence explicitly supports it. Low-quality cases may inform qualitative context only and must never determine a Stable classification alone.

## 28. Confidence Calculation

Confidence is aggregated by deterministic code from:

- evidence coverage;
- source quality;
- freshness;
- semantic consistency;
- contradiction count;
- unresolved-claim count;
- Judge verdict;
- schema validity.

Example configurable weights:

    evidence_coverage = 0.30
    source_quality = 0.20
    freshness = 0.15
    semantic_consistency = 0.15
    contradiction_penalty = -0.15
    unresolved_claim_penalty = -0.15

Approval requires sufficient evidence coverage, no critical contradiction, acceptable source quality and freshness, required Judge approval, and valid schema output.

## 29. Adaptive-Debate Policy

Routing rules:

- Missing evidence -> retrieval.
- Incomplete Supporting result -> the relevant Supporting Agent only.
- Conflicting evidence -> contradiction retrieval and Judge.
- Repeated Judge disagreement -> Consulting escalation.
- Unresolved uncertainty after limits -> UNVERIFIABLE.
- Unsupported external claim -> remove from final output.
- Approved claim -> continue without unnecessary debate.

Deterministic code selects routes. LLMs provide structured assessments but do not control loop limits.

## 30. Retry and Termination Policy

Initial configurable defaults:

    max_supporting_retries = 2
    max_debate_rounds = 3
    max_retrieval_attempts = 2
    tool_timeout_seconds = 15 to 60 by tool

Every retry records node, reason, attempt, and resulting status. No graph edge may create an unbounded loop. Partial completion is valid when independent branches succeed.

## 31. Readiness and Risk Classification

Keep Stable, Appropriate, and Risk but expose criteria.

- Stable: high critical-requirement coverage, no unresolved high-impact claim, and feasible improvement within the preparation period.
- Appropriate: meaningful fit with manageable gaps and feasible preparation.
- Risk: critical gap, insufficient preparation time, unverified credential, serious contradiction, or low evidence coverage.

No label implies acceptance or employment.

## 32. Planner Agent Responsibilities

The Planner:

- verifies recommended links, dates, application periods, and duration;
- creates preparation milestones;
- generates realistic schedules and Todo items;
- distinguishes verified external events from user-created milestones;
- preserves undated and tentative opportunities;
- sends only approved recommendations to the final report; and
- creates calendar proposals rather than silently writing events.

Externally sourced deadlines must be verified before calendar creation.

## 33. Todo Data Model

Each task contains:

    task_id
    category
    title
    reason
    related_gap_id
    evidence_refs
    priority
    estimated_effort
    target_start_date
    target_completion_date
    external_deadline
    date_type
    status
    dependencies
    calendar_proposal_id

Date types:

    VERIFIED_EXTERNAL_DATE
    PLANNER_SUGGESTED_DATE
    USER_CONFIRMED_DATE
    UNDATED
    TENTATIVE
    EXPIRED

## 34. Calendar-Integration Boundary

Calendar flow:

1. Planner creates a proposal.
2. UI shows evidence and date type.
3. User approves.
4. OAuth authorization is verified.
5. Backend writes only verified or user-confirmed events.
6. API failures preserve the proposal and Todo state.

MVP should define the boundary and proposal schema without requiring automatic writes. Production can add OAuth and event retry workers.

## 35. Final Report Schema

The response contract contains:

    request_id
    workflow_status
    profile_summary
    target_role
    preparation_period
    metadata
    market_analysis
    selected_companies
    requirements
    reference_cases
    strengths
    gaps
    supporting_findings
    readiness_classification
    recommendations
    activity_plan
    timeline
    todo_items
    calendar_proposals
    claims
    citations
    warnings
    uncertainty_notes
    agent_status

Every statement must be labeled as one of:

    CV_EXTRACTED
    USER_PROVIDED
    USER_CORRECTED
    EXTERNALLY_VERIFIED
    ANALYSIS
    RECOMMENDATION
    PLANNING_ASSUMPTION
    UNVERIFIABLE

The final synthesis node may reference only approved claims and state objects. A final claim-reference validator must reject new factual assertions.

## 36. Frontend Integration

Retain the current page flow and styling while adding:

- workflow creation and status polling;
- metadata category cards;
- edit, delete, add, and confirm controls;
- progress steps and per-agent status;
- citation links and source-quality labels;
- partial-error and warning display;
- verified, suggested, tentative, and expired date labels;
- final report, opportunities, timeline, and Todo rendering.

Server-provided text must be safely escaped before HTML insertion. Demo fallback must never be rendered as live evidence.

## 37. Backend API Design

New routes:

    POST /api/workflows
    GET /api/workflows/{id}
    GET /api/workflows/{id}/events
    PATCH /api/workflows/{id}/metadata/items/{item_id}
    DELETE /api/workflows/{id}/metadata/items/{item_id}
    POST /api/workflows/{id}/metadata/items
    POST /api/workflows/{id}/metadata/confirm
    POST /api/workflows/{id}/resume
    POST /api/workflows/{id}/calendar/proposals/{proposal_id}/approve
    POST /api/workflows/{id}/calendar/proposals/{proposal_id}/write
    DELETE /api/workflows/{id}

Existing routes remain compatibility adapters during migration. New responses include request ID, workflow status, warnings, errors, and structured sections.

## 38. Persistence and Checkpoint Strategy

MVP:

- SQLite checkpoint store.
- Workflow ID and graph thread ID.
- Secure temporary PDF reference.
- Revisioned metadata mutations.
- Checkpoints after extraction, confirmation, research, review, planning, and calendar approval.

Production:

- PostgreSQL checkpoint store.
- Encrypted object storage for PDFs.
- Background workers and queueing.
- Retention/deletion jobs.
- Distributed tracing and operational dashboards.

## 39. Prompt Organization

Create versioned prompt modules:

    app/prompts/shared.py
    app/prompts/leading.py
    app/prompts/consulting.py
    app/prompts/supporting.py
    app/prompts/judge.py
    app/prompts/planner.py

Each prompt defines input contract, output schema, forbidden behavior, provenance requirements, and concise examples. Hidden chain-of-thought is not stored or required.

Model assignment is configuration-driven:

    LEADING_MODEL
    CONSULTING_MODEL
    JUDGE_MODEL
    PLANNER_MODEL
    SUPPORTING_MODEL

Model names must not be embedded in business logic.

## 40. Error Handling

Handle malformed, password-protected, empty, image-only, and unsupported-language PDFs; extraction and schema failures; metadata conflicts; no active postings; insufficient company/reference counts; inaccessible pages; missing dates; expired opportunities; conflicting deadlines; low-quality sources; search/model/tool timeouts; Supporting Agent failure; Judge disagreement; retry exhaustion; Calendar API failure; frontend disconnection; and partial graph completion.

Default behavior is to preserve partial verified results and state uncertainty rather than fabricate a complete result.

## 41. Privacy and Security

- Validate PDF type, size, and content.
- Store uploaded PDFs temporarily and encrypt durable storage.
- Apply explicit retention and deletion policies.
- Redact CV text and personal data from logs.
- Send only necessary content to models and retrieval providers.
- Keep API keys in environment variables or secret storage.
- Restrict calendar OAuth scopes.
- Separate user source data from external evidence.
- Never expose full CV text externally when a relevant excerpt is sufficient.

## 42. Observability

Record structured events for:

- graph node execution;
- tool and model calls;
- retrieval queries and source IDs;
- Judge verdicts;
- retries and debate reasons;
- confidence values;
- state transitions;
- latency;
- token usage; and
- errors.

Redact PII and raw CV text by default.

## 43. Evaluation Metrics

- Metadata extraction accuracy.
- Metadata normalization consistency.
- Provenance accuracy.
- User-correction persistence.
- Claim precision.
- Unsupported-claim rate.
- Citation correctness and coverage.
- Contradiction-detection rate.
- Stale-evidence detection rate.
- Expired-posting recommendation rate.
- Source-authority distribution.
- Active-posting verification accuracy.
- Schema-valid output rate.
- Supporting Agent approval and retry rate.
- Average debate rounds.
- Graph completion rate.
- Planner date-verification accuracy.
- Calendar write accuracy.
- End-to-end latency.
- Cost per completed workflow.

## 44. Test Strategy

Required fixtures and integration cases:

- Two differently formatted CVs with equivalent experience.
- Korean and English CVs.
- Empty, malformed, password-protected, and image-only PDF.
- Missing target role and invalid preparation period.
- Duplicate metadata and uncertain dates.
- User correction, deletion, addition, and CV/user conflicts.
- No active posting, fewer than 10 companies, and fewer than 20 reference cases.
- Expired posting returned by search.
- Search snippet contradicted by original page.
- Conflicting dates from multiple sources.
- Only low-quality sources.
- Fabricated Supporting Agent URL.
- Fabricated user experience.
- Unsupported recommendation.
- Malformed Judge JSON.
- Supporting Agent retry exhaustion.
- One parallel branch failure.
- Calendar API failure.
- Final synthesis introducing a new claim.

Use unit tests for deterministic policies and schemas, integration tests for graph routing, retrieval fixtures, and prompt regression tests for structured model output.

## 45. Phased Implementation Roadmap

### Phase 0 — Repository and Demo Assessment

Objective: verify current behavior, encoding, routes, environment usage, and reusable UI.

Files: README.md, server.py, all HTML/JS/CSS.

Acceptance: compatibility map, encoding decision, and endpoint smoke tests.

Risks: mojibake and fallback data being mistaken for product behavior.

### Phase 1 — Input and Metadata Normalization

Objective: implement PDF validation, extraction, schema validation, provenance, review UI, and checkpoint pause/resume.

Files: diagnosis.html, script.js, server.py, new metadata/schema modules.

Acceptance: confirmed metadata survives correction, deletion, addition, and graph resume.

### Phase 2 — LangGraph Foundation

Objective: add typed state, node interfaces, configuration, checkpointing, and deterministic routing.

Acceptance: extract -> interrupt -> confirm -> resume works without one synchronous request.

### Phase 3 — Claims and Evidence Ledger

Objective: add claim/evidence models, provenance, verification status, and rejection reasons.

Acceptance: high-impact claims cannot be approved without evidence.

### Phase 4 — Internet Retrieval

Objective: add source registry, search, original-page retrieval, deduplication, freshness, active-status checks, and contradiction search.

Acceptance: stale, expired, conflicting, inaccessible, and low-quality sources are classified correctly.

### Phase 5 — Consulting Agent

Objective: add deterministic company scoring, market requirements, reference-case policy, and gap selection.

Acceptance: company and gap decisions are inspectable and respect configured limits.

### Phase 6 — Supporting Agents

Objective: add scoped prompts, parallel fan-out, structured output, and branch isolation.

Acceptance: only selected agents run and one branch failure does not erase independent results.

### Phase 7 — Judge and Adaptive Debate

Objective: add atomic verification, contradiction handling, retries, escalation, and termination safeguards.

Acceptance: unsupported claims are removed and no loop exceeds configured limits.

### Phase 8 — Classification and Planning

Objective: add readiness classification, recommendation prioritization, date provenance, dependencies, and Todo generation.

Acceptance: plan feasibility reflects preparation period and verified dates.

### Phase 9 — Calendar Integration

Objective: add OAuth, proposal review, user approval, event writes, and failure recovery.

Acceptance: no unverified external deadline is written to Google Calendar.

### Phase 10 — Final Report and UI Integration

Objective: render report, citations, warnings, progress, partial errors, opportunities, and Todo items.

Acceptance: existing pages display live workflow results without static demo content.

### Phase 11 — Evaluation and Hardening

Objective: complete reliability, privacy, tracing, prompt regression, cost, and latency work.

Acceptance: release checklist and measurable evaluation report are available.

## 46. Concrete File-Level Modification Plan

### Existing files

| Path | Planned change | Phase |
|---|---|---|
| server.py | Keep HTTP compatibility routes; delegate to modular services and graph runner | 1–4 |
| script.js | Add workflow creation, polling, metadata mutations, resume, and final rendering | 1, 10 |
| diagnosis.html | Add preparation period, metadata review, additional information, and confirmation | 1 |
| report.html | Replace static report with final response rendering | 10 |
| opportunities.html | Render verified recommendations, citations, and date status | 8–10 |
| plan.html | Render Todo, timeline, dependencies, and calendar proposals | 8–10 |
| index.html | Preserve landing/job discovery and remove misleading demo wording | 0, 10 |
| jobs.js | Add active-status/evidence fields while retaining search/filter behavior | 4, 10 |
| styles.css | Add metadata editor, progress, warning, citation, and provenance styles | 1, 10 |
| README.md | Document architecture, setup, APIs, privacy, and workflow | 0–11 |
| .env.example | Add model, retrieval, limits, checkpoint, retention, and tracing settings | 2–9 |
| requirements.txt | Pin compatible LangGraph, LangChain core, Pydantic, PDF, HTTP, and test packages | 1–2 |

### Proposed new files

    app/config.py
    app/api/routes.py
    app/api/schemas.py
    app/graph/state.py
    app/graph/builder.py
    app/graph/nodes.py
    app/graph/routing.py
    app/graph/checkpoints.py
    app/agents/leading.py
    app/agents/consulting.py
    app/agents/supporting.py
    app/agents/judge.py
    app/agents/planner.py
    app/metadata/models.py
    app/metadata/extraction.py
    app/metadata/merge.py
    app/metadata/validation.py
    app/evidence/claims.py
    app/evidence/models.py
    app/evidence/ledger.py
    app/retrieval/registry.py
    app/retrieval/search.py
    app/retrieval/fetch.py
    app/retrieval/extract.py
    app/retrieval/freshness.py
    app/prompts/shared.py
    app/prompts/leading.py
    app/prompts/consulting.py
    app/prompts/supporting.py
    app/prompts/judge.py
    app/prompts/planner.py
    app/security.py
    app/observability.py
    tests/fixtures/
    tests/unit/
    tests/integration/
    tests/prompts/

Create these incrementally. Do not perform a one-shot rewrite of the current application.

## 47. Future Grammar and Expression Agent

Reserve an always-running final CV writing extension point. It may inspect grammar, wording, structure, and flow, but it must preserve factual content, metadata item IDs, claims, and evidence references. It may not invent achievements, strengthen unsupported claims, or alter confirmed facts.

## 48. Dependencies and Version Considerations

LangGraph is not currently installed. Phase 2 must first inspect the repository Python version and select a compatible stable version. Pin LangGraph and supporting dependencies in requirements.txt after compatibility testing; do not assume the latest SDK API.

Initial dependency categories:

- LangGraph.
- LangChain core.
- Pydantic.
- PDF parser and optional OCR support.
- HTTP client.
- SQLite/PostgreSQL checkpoint adapter.
- Test tooling.
- Optional tracing provider.

## 49. Open Questions and Assumptions

Defaults:

- Start the source registry with Work24, official company recruitment pages, and approved public recruitment sources.
- Official and attributable reference cases are strong evidence; anonymous cases are context-only.
- Calendar writes require explicit user approval.
- SQLite is the MVP checkpoint store; PostgreSQL is the production path.
- Uploaded PDFs use short configurable retention.
- Existing static frontend and startup command remain during migration.
- Stable/Appropriate/Risk labels remain with visible criteria and warnings.
- CV Positioning & Expression runs initially; the broader Grammar Agent is deferred.
- Manual CV entry becomes additional information, not a replacement for PDF input.
- Fallback data is never presented as verified evidence.

Resolve during Phase 0 or Phase 2:

- Approved source domains and per-domain limits.
- PDF parser and OCR strategy.
- Compatible LangGraph/Python versions.
- Production database and object-storage provider.
- Google Calendar OAuth deployment model.
- Retention period and deletion SLA.
- Whether the encoding issue requires a separate migration.

## 50. First Implementation Milestone

Phase 1 is the first milestone: PDF input and confirmed metadata review.

It is complete when a user can upload a valid PDF, enter a role and preparation period, receive schema-valid metadata with provenance and page references, edit it through the UI, confirm it, and resume a persisted graph using only the confirmed profile.

This establishes the core architectural boundary for all later agents.

