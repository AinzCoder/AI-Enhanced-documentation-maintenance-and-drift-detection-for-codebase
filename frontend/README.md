# DocGuard frontend

The DocGuard frontend is a Next.js App Router application using TypeScript,
Tailwind CSS, Axios, and the existing project dependencies.

## Local setup

From this directory, install dependencies and start the development server:

```powershell
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The backend defaults to
`http://127.0.0.1:8000`. To use another backend URL, copy `.env.example` to
`.env.local` and set `NEXT_PUBLIC_API_BASE_URL`. Local environment files are
ignored by Git.

The dashboard makes only a read-only `GET /` request to display backend
connectivity. Analysis, indexing, documentation generation, approval, and
rejection are not triggered automatically.

## Workspace navigation

Select a local path under **Repository**, then use **Analysis** for full scans,
coverage, Git drift, or the search index. **AI Documentation** provides
generation, review, decision history, and change suggestions. To review a
saved preview, select its repository and retrieve it by generation ID.
Approval remains explicit and verifies source and target hashes.

The selected repository is held in the current browser session and is not
restored after a full page reload. History shows decisions across repositories;
pending previews are retrieved by ID rather than listed there.

Hosted mode uses an OIDC login and same-origin server proxy; see the project
README for required configuration and limitations. Hosted repository imports
remain disabled, and no live identity provider has been validated. The
repository selector shows GitHub URL and ZIP options in hosted mode, but neither
submits an import until secure endpoints and verified quota-backed workspaces
are available. ZIP file validation in the interface uses a preliminary 25 MiB
limit; it is not a backend security limit. ZIP imports will not provide Git
history, so Git-based analysis may be unavailable.

In trusted local mode, select **Local Repository Path** and enter an absolute
path accessible to the backend (including Windows paths). The GitHub option
is visible but importing remains unavailable.

Preview and change-suggestion generation send selected source and
documentation context to Groq. The Groq API key belongs only in the backend
environment; the frontend must never be configured with it.

## Validation

```powershell
npx tsc --noEmit
npm run lint
npm run test:run
npm run build
```
