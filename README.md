# HICAREER

HICAREER is currently a repository-local MVP for CV/job-fit analysis and career-growth recommendations. The current implementation is a static frontend served by a small Python standard-library backend.

The target LangGraph architecture is defined in MASTER_PLAN.md. LangGraph is not implemented in the current Phase 0 work.

## Current repository architecture

### Frontend

The frontend uses static HTML, vanilla JavaScript, and CSS. There is no frontend framework or bundler.

- index.html: landing page and popular-job search.
- diagnosis.html: CV input and analysis entry point.
- report.html: currently static sample report.
- opportunities.html: currently static sample opportunity page.
- plan.html: currently static sample growth-plan page.
- styles.css: shared layout, forms, cards, loading, and responsive styles.
- jobs.js: popular-job search, cache, filters, and job-card rendering.
- script.js: CV upload, PDF extraction, manual form handling, analysis request, and result rendering.

### Backend

The backend is server.py using Python http.server.SimpleHTTPRequestHandler and ThreadingHTTPServer. It serves static files from the repository root and calls external services directly through Python standard-library HTTP utilities.

Current API routes:

| Method | Route | Current behavior |
|---|---|---|
| GET | /api/jobs/popular?limit=&keyword= | Retrieves jobs from configured sources and falls back to sample jobs |
| POST | /api/extract-cv | Accepts a multipart PDF and uses OpenAI file input to map it to editable fields |
| POST | /api/analyze-cv | Accepts JSON or multipart CV input, ranks jobs, creates heuristic agent data, and optionally creates an LLM report |

Current integrations are Work24, Saramin/JobKorea scraping, and the OpenAI Responses API.

## Running the current MVP

### Windows PowerShell

    python -m pip install -r requirements.txt
    $env:PORT = "8080"
    python server.py

Open http://localhost:8080/.

### macOS/Linux

    python3 -m pip install -r requirements.txt
    PORT=8080 python3 server.py

Open http://localhost:8080/.

The current requirements.txt does not install LangGraph. LangGraph must be evaluated and added only in a later implementation phase.

## Environment configuration

The available environment variables are:

| Variable | Purpose | Required |
|---|---|---|
| HOST | HTTP bind address; defaults to 0.0.0.0 | No |
| PORT | HTTP port; defaults to 8080 | No |
| JOBS_CACHE_TTL_SECONDS | Popular-job cache duration; defaults to 600 | No |
| WORK24_AUTH_KEY | Work24 API credential | No |
| OPENAI_API_KEY | OpenAI Responses API credential | Required for current PDF extraction and LLM report |
| OPENAI_MODEL | Current model configuration | No |

Real credentials must not be committed. The current implementation reads credentials from environment variables and has no secrets manager.

## Current request and response behavior

### Popular jobs

The frontend calls:

    GET /api/jobs/popular?limit=12&keyword=<encoded keyword>

The response is a JSON array. Current job objects contain title, company, category, location, deadline, fit, skills, reason, url, and source.

The backend attempts Work24, Saramin, and JobKorea retrieval depending on configuration and network availability. On failure it returns sample fallback data. Fallback data is demo data, not verified market evidence.

### PDF extraction

Request:

    POST /api/extract-cv
    Content-Type: multipart/form-data

Multipart fields:

- cv_file: uploaded PDF.
- target_role: optional target role.

Current response fields include source, filename, pdf, text, and fields. The fields object contains targetRole, education, projects, work, activity, strength, extra, and rawSummary.

This is a demo field mapper. It is not yet the provenance-aware canonical metadata model required by the product.

### CV analysis

Request:

    POST /api/analyze-cv
    Content-Type: application/json

Example input:

    {"target_role":"AI Engineer","cv_text":"Python project experience"}

The endpoint also accepts multipart input with a CV file and target_role.

The response includes source, filename, summary, rankedJobs, agent, and llmReport. The current implementation uses heuristic phrase overlap, cosine similarity, scraped/fallback jobs, and an optional single LLM report.

It does not yet provide workflow IDs, LangGraph state, checkpointing, metadata-review interrupts, claim IDs, evidence IDs, Judge verification, adaptive debate, readiness policy, Planner state, calendar proposals, or protected user-confirmed metadata.

## Phase 0 verification results

The following checks were run:

- python -m py_compile server.py: passed.
- Static root request: HTTP 200.
- GET /api/jobs/popular?limit=1&keyword=AI: HTTP 200.
- POST /api/analyze-cv with minimal JSON input: HTTP 200.
- Main source files were readable as UTF-8.
- No UTF-8 replacement characters were found.
- Mojibake-like strings were found in server.py, script.js, jobs.js, HTML files, and README.md.

The encoding issue should be investigated before changing user-facing Korean copy. It may be an earlier text conversion problem rather than a runtime UTF-8 failure.

## Reuse and migration map

### Reuse

- Existing static page structure and startup command.
- Navigation and shared visual conventions.
- PDF upload control.
- Job cards, filters, cache behavior, and loading states.
- Existing multipart parsing as an interim compatibility mechanism.
- Existing job adapters as retrieval-provider candidates.
- Existing environment-variable configuration pattern.

### Modify

- diagnosis.html: add preparation period and metadata review/confirmation.
- script.js: replace one-shot analysis with workflow status, metadata mutations, and resume.
- report.html: render live report sections and citations.
- opportunities.html: render evidence-backed opportunities and freshness/status.
- plan.html: render Planner Todo and calendar proposals.
- jobs.js: retain filtering/cache behavior and add source/verification status.
- styles.css: add metadata editor, progress, warning, citation, and provenance styles.
- server.py: retain compatibility routes while delegating workflow logic to modular services.

### Demo-only or deprecated behavior

- Static sample report, opportunity, and plan content.
- Manual CV entry as a primary replacement for PDF.
- Free-form PDF bullet mapping as canonical metadata.
- Single unrestricted LLM report generation.
- Simple similarity score as a factual readiness decision.
- Fallback jobs displayed without an explicit fallback label.

## Current limitations and risks

1. The current backend is a monolithic standard-library HTTP handler.
2. LangGraph and checkpoint persistence are not installed.
3. PDF extraction does not preserve robust page/location provenance.
4. Current metadata is editable text blocks rather than structured item records.
5. There is no graph interrupt or human-in-the-loop persistence.
6. There is no claim-level evidence verification.
7. Search and scraping are network-sensitive and provider-specific.
8. Fallback jobs may be mistaken for live evidence unless clearly labeled.
9. LLM JSON output is not governed by the final Judge contract.
10. Frontend HTML interpolation requires safe rendering before displaying external content.
11. There is no persistent workflow state, resumability, or background execution.
12. Google Calendar integration does not exist.
13. CV retention, deletion, and logging-redaction policies are not implemented.
14. Korean text encoding requires a dedicated verification or migration decision.

## Phase 1 metadata workflow

Phase 1 adds a PDF-to-metadata review workflow without adding LangGraph or downstream agents.

New endpoints:

| Method | Route | Purpose |
|---|---|---|
| POST | /api/workflows | Validate a PDF, extract text, normalize metadata, and return a review-required workflow |
| GET | /api/workflows/{id} | Return the current workflow and metadata state |
| PATCH | /api/workflows/{id}/metadata/items/{item_id} | Update one unconfirmed metadata item |
| DELETE | /api/workflows/{id}/metadata/items/{item_id} | Delete one unconfirmed metadata item |
| POST | /api/workflows/{id}/metadata/items | Add user-provided metadata |
| POST | /api/workflows/{id}/metadata/confirm | Confirm the current metadata revision |

The workflow response contains raw extraction information, normalized metadata, provenance, extraction confidence, warnings, revision, and (after confirmation) user-confirmed metadata.

Phase 1 uses an in-memory workflow store. It supports revision checks and HTTP 409 conflicts, but it is not durable across process restarts. Durable LangGraph checkpointing is intentionally deferred to Phase 2.

The PDF extractor uses pypdf. Image-only PDFs return a warning and require user-provided metadata because OCR is not included in this phase. The existing /api/extract-cv endpoint remains available as a compatibility adapter for the previous demo flow.

## Collaborator agent-discussion integration

The latest origin/main contains four collaborator commits adding a multi-agent discussion presentation to the older diagnosis and analysis flow:

- 722eda9 Add multi-agent career discussion flow
- c6ec3fa Expand job ranking and review sources
- f24758d Make agent discussion conversational
- a721a4b Refocus agents on spec-building discussion

Those commits were fetched for inspection but were not merged wholesale because they modify the same files as the Phase 1 metadata workflow and assume the previous manual-input/analyze-cv page flow. They also include generated market and review messages that are not yet backed by the Phase 1 Evidence Ledger.

The compatible portion is integrated as a Phase 1 handoff panel:

- GET /api/workflows/{id}/discussion returns a typed discussionHistory contract.
- The panel appears after metadata confirmation.
- Leading Agent 1 reports the confirmed metadata handoff.
- Leading Agent 2 and Supporting Agents remain PENDING until later graph phases provide verified market evidence and gap selection.
- Each displayed event includes status, timestamp, and metadata evidence references where applicable.
- No external company, acceptance-case, deadline, or recommendation claim is generated by this Phase 1 panel.

The remote market-research conversation UI can be extended later by replacing the handoff payload with approved Consulting/Judge events without changing the frontend rendering contract.

## Recommended next step

Proceed to Phase 1 in MASTER_PLAN.md:

1. Add PDF validation.
2. Introduce raw extraction, normalized metadata, and confirmed metadata schemas.
3. Preserve source page/location references where possible.
4. Add category-based user metadata review.
5. Add role and preparation-period validation.
6. Keep the existing API routes as compatibility adapters while introducing workflow-oriented endpoints.

Do not add LangGraph, Consulting, Supporting Agents, Planner, or Calendar functionality until the confirmed metadata boundary is implemented and tested.
