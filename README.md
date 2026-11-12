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
| `DOCGUARD_MODE` | unset | Must be `local` for trusted local path access or `hosted` for the experimental authenticated API. Unset or invalid values fail closed. Set in the process environment. |

Start the backend:

```powershell
Set-Location backend
$env:DOCGUARD_MODE = "local"
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

In explicitly enabled local mode, select a repository path accessible to the backend and run analysis explicitly.
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

## Experimental hosted authorization

The backend has a **foundation only**, not a deployable hosted application.
Set `DOCGUARD_MODE=hosted`, `DOCGUARD_OIDC_ISSUER`,
`DOCGUARD_OIDC_AUDIENCE`, `DOCGUARD_OIDC_ALGORITHMS` (comma-separated
asymmetric JWT algorithms), `DOCGUARD_WORKSPACE_ROOT` (an existing absolute
directory), and `DOCGUARD_WORKSPACE_DATABASE` (an absolute SQLite path whose
parent exists). Missing or unsafe configuration rejects repository requests.
The issuer must be HTTPS; discovery and JWKS requests do not follow redirects
and the JWKS host must match the issuer host or be listed in the optional
comma-separated `DOCGUARD_OIDC_JWKS_HOSTS` allowlist. Use access tokens,
not unverified identities or client-supplied user IDs.

Hosted clients must send `Authorization: Bearer <access-token>` and use
`repository_id` instead of `repository_path` in analysis, RAG, suggestion,
and generation requests; `/rag/status` accepts `repository_id` as a query
parameter. Repository IDs are random opaque identifiers mapped in SQLite to
an issuer/subject owner, expiry and a server-managed directory. Generation
previews and decisions are checked against the same ownership mapping.
Hosted `/history` omits local and other users' records. The legacy `/decision`
endpoint is unavailable in hosted mode; use generation preview approval.
Hosted repository registration, imports, and removal are disabled. The
frontend's hosted mode uses a same-origin Next.js proxy that sends the API
access token to FastAPI and converts selected opaque IDs to `repository_id`.

The workspace database and directories must be writable only by trusted
service processes. Provisioning is not exposed as an HTTP API and no real
quota enforcement is included. Access tokens and workspace
metadata require appropriate protection and backup. A production design
still needs resource isolation, quotas, secure ingestion, operational recovery,
and a security review before exposure.

### Ingestion and quota work still required

The internal ingestion service uses a provisioner interface for staging,
readiness checks, publication and cleanup. It streams ZIP bytes into staging
with a compressed-size cap and uses the ZIP helper to validate file types,
paths, count and expanded bytes. It discards staging on failure. The helper
rejects `.git` metadata, so ZIP imports do not preserve Git history; full scans
and coverage can work, but Git-based change detection needs a Git repository.

The internal Git service uses a validated GitHub URL, argument-list subprocess,
disabled redirects, isolated Git configuration, disabled hooks, submodules and
LFS smudging, and a timeout that kills the process group. It fetches at most two
commits; comparisons requiring older commits may be unavailable. These services
are not exposed through HTTP. The default production provisioner always fails
closed: the included fake provider is only for disposable tests. Process-local
concurrency limiting is not sufficient for multiple workers or replicas.

Hosted GitHub cloning and ZIP upload remain disabled. Before enabling either,
deployment must provide and independently verify hard limits *during* writes:
an aggregate workspace capacity, an allocation per owner, and an individual
limit per import. A shared Docker bind mount or a post-import size check does
not satisfy these requirements. One possible Linux design is separately
capacity-limited storage for each owner with per-import filesystem project
quotas, provisioned and checked by a privileged storage service; the aggregate
capacity and owner allocations must also be independently enforced. The
backend must fail closed if the mounted storage, active quota settings, hard
limits or owner assignment cannot be verified. No such provisioner or
verification exists in this project yet, and its exact implementation must
be validated on the deployment filesystem before use.

For a Linux deployment, use an owner-isolated, capacity-limited filesystem or
volume for each owner, with XFS project quotas enabled (`prjquota`) and a unique
project ID and hard block/inode limit for each import's staging and published
tree. The total capacity of the workspace pool must separately enforce the
aggregate limit; filesystem project quotas alone do not provide nested owner
and aggregate accounting. The privileged provisioner, not the web process,
must allocate project IDs, assign quota inheritance before any writes, reserve
owner capacity atomically, set hard limits, and publish ownership metadata and
repository paths crash-safely. Place upload archives and Git object writes
inside the same quota-controlled import staging tree. Keep application files,
SQLite and ChromaDB outside imported storage.

Before enabling an implementation, an operator must verify the actual mount
inside the container and host (for example `findmnt -T <workspace-root> -o
TARGET,SOURCE,FSTYPE,OPTIONS`), confirm project quota accounting and enforcement
using `xfs_quota -x -c 'state -p' <mount>`, and inspect the assigned hard
limits and usage with `xfs_quota -x -c 'report -p -b -i' <mount>`. Validate
the independent owner and pool limits using their storage manager's own quota
reporting. On disposable, separately assigned workspaces, write until the
kernel rejects blocks and inodes, confirm a different owner's allocation
remains usable, restart the container/host and repeat, and test cleanup and
recovery after interruption. Never run these write tests on production data.
The eventual provider must verify the same mount, quota enforcement, project
assignment, hard limits, owner reservation, and lifecycle recovery on startup
and at allocation/publication time. These steps require Linux infrastructure;
they were not performed on this Windows development machine.

Do not enable imports until durable expiry cleanup, safe deletion while
operations are active, cross-process concurrency limits, filesystem isolation,
quota verification, and live OIDC integration are implemented and independently
tested. A quota flag or the included byte limits are not proof of enforcement.

### Deployment readiness checklist

- **Verified offline:** hosted JWT and workspace-owner checks, opaque-ID proxy
  translation, repository-scoped RAG and approval isolation, and local-path
  compatibility. Internal Git and ZIP imports have been exercised through
  analysis with a disposable fake provisioner; this is not a real storage provider.
- **Identity provider required:** select and configure an OIDC provider issuing
  API-audience JWT access tokens; verify the real login, expiry, logout and
  authorization flow end to end. Current sessions do not refresh or revoke tokens.
- **Linux infrastructure required:** implement and independently verify the
  quota-backed provisioner, mount, per-import, per-owner and aggregate hard
  limits using the commands and disposable write tests above. Secure the
  provisioner's privileges, filesystem permissions, storage and backups.
- **Application work required:** implement authenticated import endpoints and
  frontend submission only after quota verification, durable crash/expiry
  recovery, safe deletion during active operations, and cross-worker/replica
  concurrency controls. Evaluate CPU, memory, process and indexing limits for
  untrusted repositories, and complete an independent security review.

Do not expose hosted imports or claim deployment readiness until these checks
pass on the actual deployment environment.

### Frontend OIDC configuration

The hosted frontend uses NextAuth.js with OIDC authorization code, PKCE,
state, and nonce. It requires a confidential OIDC client configured with
`https://<frontend-host>/api/auth/callback/oidc` as its redirect URI. Configure:

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_DOCGUARD_MODE` | Set to `hosted` at build time; `local` preserves the existing local workflow. |
| `NEXTAUTH_URL` | Public HTTPS frontend origin. |
| `NEXTAUTH_SECRET` | Random server-only session encryption secret, at least 32 characters. |
| `OIDC_ISSUER` | HTTPS issuer, exactly matching `DOCGUARD_OIDC_ISSUER` on FastAPI. |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | OIDC confidential client credentials; keep the secret server-side. |
| `OIDC_API_AUDIENCE` | FastAPI audience, matching `DOCGUARD_OIDC_AUDIENCE` and different from the OIDC client ID. |
| `OIDC_AUDIENCE_PARAMETER` | Set to `audience` or RFC 8707 `resource`, according to the provider. |
| `OIDC_SCOPES` | Optional provider-specific scopes; default `openid profile email`. |
| `DOCGUARD_BACKEND_URL` | Private server configuration for the HTTPS FastAPI origin; no path or credentials. |

The provider must support code flow with PKCE and issue a JWT **access token**
for the configured API audience. Auth.js stores the access token in an
encrypted HTTP-only session cookie, not in localStorage or the browser-facing
session. The server proxy forwards it as a bearer token; FastAPI independently
verifies its signature, issuer, audience and expiry. Expired or missing access
tokens require signing in again; refresh tokens are not stored or refreshed.
Signing out ends the browser session but does not revoke the provider token or
terminate the provider's own login. The stateless session has no server-side
revocation. Hosted API 401 and 403 responses remain distinct.

No live provider has been configured or verified. The frontend must be
rebuilt when public mode changes. The same-origin proxy requires HTTPS to the
backend and may be subject to Vercel execution-duration limits, especially for
long generation requests. Provisioning/imports remain disabled; no hosted
workflow can be used until workspaces are safely provisioned.

## Limitations and deployment prerequisites

- Local mode permits arbitrary backend-accessible filesystem paths without
  authentication and must only be used on a trusted machine and network.
  Do not expose it publicly. Hosted mode is experimental and incomplete.
- Repository paths refer to the **backend host**, not the user's browser.
  Frontend path handling and development have been tested on Windows; other
  operating systems and cloud repository access need validation.
- `backend\data` stores the repository registry and histories; `backend\chroma_db`
  stores Chroma data. Both require writable, persistent storage and backup
  planning. The local Hugging Face model cache must also be available or
  downloadable. These paths currently reside under the backend or user profile.
- CORS currently allows only localhost frontend origins. The hosted frontend
  uses a server-side proxy; direct browser access would need configured CORS.
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
