# DocGuard

DocGuard analyzes local Java repositories for documentation coverage and
drift, and helps developers review AI-generated documentation. Repository
analysis works without Groq. Generating documentation sends selected source
code and documentation context to Groq; use it only with authorization.

## Features

- Java repository scanning and Tree-sitter parsing, Git change analysis,
  documentation coverage and drift detection.
- Repository-scoped local semantic retrieval and incremental Markdown indexing.
- Source-grounded Groq documentation previews and optional repository overview.
- Explicit developer approval or rejection, stale-content checks, atomic
  Markdown updates, and SQLite generation and audit history.

## Architecture and stack

The Next.js 16 / React 19 / TypeScript frontend calls a Python 3.13 FastAPI
backend. The backend scans a repository available on its own filesystem,
parses Java with Tree-sitter, and compares code, documentation and Git changes.
The RAG pipeline uses local `BAAI/bge-small-en-v1.5` sentence-transformer
embeddings and a persistent ChromaDB collection scoped to each repository.
Groq's `openai/gpt-oss-20b` generates documentation using selected source and
retrieved context. Previews and audit records are persisted in SQLite.

## Prerequisites

- Windows PowerShell, Python 3.13 and Git on `PATH`.
- Node.js 22 or later supported by the installed Next.js version, and npm.
- A local Java repository accessible to the backend. A JDK is not needed for
  source analysis.
- A newly rotated Groq API key for generation, and a cached or downloadable
  embedding model for RAG. Do not commit the key.

## Backend setup and execution

From the project root:

```powershell
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
```

Set `GROQ_API_KEY` in `backend\.env` or the backend process environment.
Process environment values take precedence. The example contains only variables
used by the application:

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | empty | Backend-only Groq credential; required for generation. |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Groq model. |
| `GROQ_TIMEOUT_SECONDS` | `120` | Per-request timeout. |
| `GROQ_MAX_COMPLETION_TOKENS` | `1024` | Completion budget, including reasoning tokens. |
| `GROQ_GENERATION_DEADLINE_SECONDS` | `300` | Limit for LLM attempts and retry waits in a preview. |

Start the backend:

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Frontend setup and execution

In another PowerShell terminal, from the project root:

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. `NEXT_PUBLIC_API_BASE_URL` in
`frontend\.env.local` selects the backend URL and defaults to
`http://127.0.0.1:8000`. This is a public browser setting, **not a secret**;
never put the Groq key in frontend variables. Next.js public variables are
embedded at build time, so rebuild the frontend after changing them.

## Analysis, RAG and review

Select a repository path accessible to the backend and run analysis explicitly.
DocGuard reads Java source and Markdown, computes coverage, and reports drift
using Git changes. Analysis does not call an LLM or build the RAG index.

For a preview, local RAG indexes documentation when context is needed. It
skips unchanged files and reuses unchanged chunks in changed files. The model
is loaded lazily once per backend process; its first load can be slow. Groq
generates the preview; a pending SQLite record is saved only when generation
succeeds. The developer must explicitly approve or reject it. Approval checks
source and target SHA256 hashes before an atomic Markdown update.

Groq rate limits apply to the account's remaining quota. A preview may make
one request per missing class and selected method, plus one for an enabled
overview. Start with one method and disable the overview if rate-limited.
Temporary 429 errors receive at most one bounded retry; daily limits are not
retried automatically. Repository scanning and local RAG operations cannot
be interrupted by the generation deadline.

## Testing

From the project root:

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m pytest -q
Set-Location ..\frontend
npm run test:run -- --maxWorkers=1
npx tsc --noEmit
npm run lint
npm run build
```

The CI workflow runs these checks on Windows with Python 3.13 and Node 22.
Backend tests use synthetic data and mocked provider responses; CI sets
Hugging Face offline mode to prevent accidental model downloads. It does not
need a Groq key or deploy the application.

## Limitations and deployment prerequisites

- This is a local application, not an internet-ready multi-user service. The
  backend has no authentication or authorization and accepts filesystem paths.
  Do not expose it publicly without access control, isolation, and a security
  review. The legacy decision workflow is separate from preview approval.
- Repository paths refer to the **backend host**, not the user's browser.
  Frontend path handling and development have been tested on Windows; other
  operating systems and cloud repository access need validation.
- `backend\data` stores the repository registry and histories; `backend\chroma_db`
  stores Chroma data. Both require writable, persistent storage and backup
  planning. The local Hugging Face model cache must also be available or
  downloadable. These paths currently reside under the backend or user profile.
- CORS currently allows only localhost frontend origins. A hosted frontend
  requires an explicitly configured origin and a separate deployment design.
  SQLite and Chroma concurrency, persistence, network access, and recovery need
  evaluation before production hosting.
- Groq inference sends source and documentation context to a third party.
  Review privacy and data-handling requirements before use.

## Troubleshooting and timings

Check backend-only key configuration and rotate exposed keys. For model errors,
check Groq model availability and local embedding-cache access. For RAG fallback,
check Chroma permissions and model connectivity.

Set `DOCGUARD_TIMING=1` before starting the backend to log stage durations.
`embedding.model_load` includes library import and construction;
`embedding.encode` measures encoding separately. `rag.index` includes its
nested operations, so do not sum nested timings. Timings do not log prompts or
source content.
