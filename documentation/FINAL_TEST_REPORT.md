# DocGuard Final End-to-End Test Report

> Historical report: this documents an earlier Ollama-based configuration,
> not validation of the current Groq migration. See the project README for
> current setup.

## Summary

| Measure | Result |
|---|---:|
| Functional test cases | 16 passed, 0 failed, 0 blocked |
| Backend regression suite | 203 passed |
| Frontend regression suite | 37 passed across 10 test files |
| TypeScript validation | Passed |
| ESLint | Passed |
| Next.js production build | Passed |
| Production HTTP smoke checks | Frontend and backend both returned HTTP 200 |
| Method documentation coverage | 1/6 (17%) before approval; 4/6 (67%) after |
| Class documentation coverage | 1/2 (50%) before approval; 2/2 (100%) after |

The functional tests used a disposable Git repository under Windows `%TEMP%` and a second isolated repository. The protected `test_repositories/OrderManagement` worktree files appeared modified in Git status; the user confirmed those changes were pre-existing. They were not altered or restored during this test.

## Environment and startup

- Python 3.13.15, Node.js 24.18.1, npm 11.16.0, and Ollama 0.34.4 were available.
- The installed `qwen2.5-coder:7b` model responded to a live readiness prompt and was used for documentation preview generation.
- The workspace-root `venv` passed dependency checks and imported the FastAPI application. The separate `backend\venv` is incomplete and lacks required runtime packages, including Tree-sitter. The backend was run with the workspace-root environment.
- No `frontend\.env.local` was present; the frontend's default API base URL (`http://127.0.0.1:8000`) worked.
- FastAPI and the Next.js production server were available on localhost ports 8000 and 3000. Final HTTP checks returned 200 for both. A fresh production browser page loaded the dashboard and displayed “Backend: Connected.”
- An actual request from the frontend origin succeeded, and the CORS preflight for `http://localhost:3000` succeeded.
- The Ollama model ran CPU-backed and generation took several minutes.

## Functional test evidence

Disposable repository inputs are identified below as the primary and isolated `%TEMP%\DocGuard-e2e-*` repositories to avoid embedding a machine-specific user path.

| Test ID | Test Description | Input | Expected Result | Actual Result | PASS/FAIL/BLOCKED | Evidence |
|---|---|---|---|---|---|---|
| TC01 | Valid repository selection | Primary disposable Git repository | UI accepts and displays the selected repository | Repository selected in the application and used for subsequent analysis | PASS | Browser repository selector and analysis workflow |
| TC02 | Full scan across multiple Java files | `src\OrderService.java`, `src\UserService.java` | Scan both Java files and report extracted entities | 2 Java files, 2 classes, and 6 methods; no scan errors | PASS | Browser analysis results |
| TC03 | Java class and method extraction | Both Java source files | Extract classes and methods from each file | 2 classes and 6 methods extracted | PASS | Browser analysis results and file explorer |
| TC04 | Missing documentation detection | Six extracted methods and existing Markdown docs | Identify undocumented methods | Baseline reported 1/6 documented methods and 5 missing methods | PASS | Browser coverage/drift view |
| TC05 | Git change detection | Disposable repo commit history with method addition, modification, and removal | Identify changed files and method-level changes | 2 changed files and 4 method changes, including added, modified, and removed methods; no errors | PASS | Browser Git comparison against base commit `3f72e9f193b3d057f708da00e576c98909027bde` |
| TC06 | Documentation drift detection | Changed Java methods and repository Markdown docs | Report missing or stale documentation | 2 drift findings were reported for `OrderService` | PASS | Browser coverage/drift view |
| TC07 | RAG indexing and status | Primary disposable repository | Index repository documents and report status | 2 documents and 6 chunks indexed; status endpoint returned successfully | PASS | UI indexing result and RAG status |
| TC08 | Documentation generation with live Ollama | Primary repository, `qwen2.5-coder:7b` | Generate a reviewable preview without automatic approval | Live model generated a preview of 3 methods (bounded by `max_methods=3`); preview remained pending until review | PASS | Browser generation preview; generation record `bec4bf4a13e34022813f0a599bca39df` |
| TC09 | Preview without writing files | Preview targeting `docs\API.md` | Preview leaves the target unchanged | SHA-256 remained `34ff88a60bcf54b318df551f6a556edaf8eb543c3d317099582937fc5ee74bdf` across preview | PASS | Target hash before and after preview |
| TC10 | Explicit approval and Markdown update | Fresh generated preview; explicit review approval in the application | Only explicit approval writes generated documentation | UI confirmation approved the preview; record became `approved`; target hash changed from `34ff88a6…` to `cb04a8bd2445e708c70bf916791d33fc90f621dadafcd4efe43d5feafc9af2b2` and file size became 4502 bytes | PASS | Browser review flow; generation record `bec4bf4a13e34022813f0a599bca39df` |
| TC11 | Reanalysis and measurable coverage improvement | Repository after approved documentation update | Reanalysis shows increased documentation coverage | Method coverage rose from 1/6 (17%) to 4/6 (67%); class coverage rose from 1/2 (50%) to 2/2 (100%) | PASS | Before/after browser coverage results |
| TC12 | Rejection without file modification | Pending preview | Rejection records the decision and leaves the target unchanged | UI rejection persisted status `rejected`; target retained its pre-approval SHA-256 | PASS | Browser review flow; generation record `78ffcf556ce74978974e4b49b8b24fa7` |
| TC13 | Stale source or target protection | Preview followed by a source change before approval | Stale preview cannot be applied | Approval returned HTTP 409, record became `stale`, and the UI reported that approval was blocked | PASS | Browser review attempt; generation record `52a2ca2ab8df40279d877e018a06c138` |
| TC14 | Repository switching and isolation | Switch from primary repo to a second disposable repo | Do not show prior analysis or mix repository indexes | Prior analysis disappeared after switching; the isolated repository had a distinct RAG identity and 0 documents/0 chunks versus primary's 2/6 | PASS | Browser repository switch and RAG status |
| TC15 | Invalid repository path handling | Nonexistent absolute repository path and relative RAG path | Reject invalid paths with an error response | Missing repository returned HTTP 404; relative RAG path returned HTTP 400 | PASS | API responses exercised during the UI/API workflow |
| TC16 | Unsafe or traversal path rejection | Generation target `../README.md` and traversal source input | Reject traversal rather than access files outside the repository | Traversal target returned HTTP 400; source traversal produced an explicit validation error and no file was read | PASS | API validation responses |

## Browser testing

The frontend was exercised through browser automation; backend API checks were not used as a substitute for UI coverage. UI workflows included dashboard navigation, repository selection, analysis, coverage/drift, RAG indexing, generation preview, explicit approval and rejection, history, repository switching, and mobile navigation. Loading, error, and empty states were also checked, including the empty analysis state after changing repositories.

Browser screenshots were captured during the session for analysis, Git changes, coverage, mobile navigation, and developer review. The browser tool surfaced these captures inline; it did not provide saved image files to include alongside this report.

The dashboard was reopened against the production build after the development server was stopped. It loaded successfully and showed the backend as connected.

## Regression validation

- Backend: 203 tests passed; one Starlette/httpx deprecation warning was reported.
- Frontend: 37 tests passed across 10 files.
- TypeScript check: passed.
- ESLint: passed.
- Next.js production build: passed.

## Defect found and fixed

Changing the selected repository outside the Analysis page left the previous repository's analysis visible. Analysis results, loading state, and error state are now scoped to the currently selected repository path. A frontend regression test covers switching repositories through the shared selection state, and it passed.

Files changed for the fix:

- `frontend/src/app/analysis/page.tsx`
- `frontend/src/app/analysis/page.test.tsx`

The report itself is the only additional file created for this deliverable.

## Limitations and demonstration readiness

- Use the workspace-root `venv` to start the backend. The separate `backend\venv` is incomplete and will not provide the runtime dependencies used for this test.
- Local Ollama generation is functional but may take several minutes on CPU.
- Browser screenshots are session captures, not image files bundled with this report.

**Readiness:** DocGuard is ready for the MCA final demonstration when started with the validated workspace-root Python environment and the local Ollama model available. The tested approval workflow required explicit application review; previews and rejected or stale proposals did not overwrite the Markdown target.
