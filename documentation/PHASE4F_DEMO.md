# DocGuard Phase 4F Demo

This walkthrough uses a disposable Java repository. Do not run generation or approval against `test_repositories\OrderManagement` or another repository containing work you need to preserve.

## Prerequisites

- Windows PowerShell, Git, Node.js, and npm.
- The project-level Python 3.13 environment configured in the project README.
- Backend dependencies importable from that environment, including FastAPI, pytest, Tree-sitter, ChromaDB, and sentence-transformers.
- A newly rotated Groq API key configured in the backend environment, and network access to Groq.

## Start the local services

Configure the backend as described in the project README, then start FastAPI
from the project root:

```powershell
Set-Location backend
& ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from the project root, start the frontend:

```powershell
Set-Location frontend
$env:NEXT_PUBLIC_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000`.

## Prepare a disposable demo repository

Run this in PowerShell. It creates a new repository under `$env:TEMP`, commits a baseline, and leaves one meaningful working-tree change for drift analysis.

```powershell
$demo = Join-Path $env:TEMP ('docguard-demo-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $demo | Out-Null

function Write-Utf8NoBom([string]$relativePath, [string]$content) {
    $path = Join-Path $demo $relativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [System.IO.File]::WriteAllText(
        $path,
        $content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

Write-Utf8NoBom 'README.md' @'
# DocGuard demo repository

A disposable order-management example.
'@

Write-Utf8NoBom 'docs\API.md' @'
# API Documentation

## OrderService

Manages orders.

### addOrder(Order order)

Stores an order by its identifier.
'@

Write-Utf8NoBom 'src\Order.java' @'
package demo;

public class Order {
    private final String id;
    private final double total;

    public Order(String id, double total) {
        this.id = id;
        this.total = total;
    }

    public String getId() { return id; }
    public double getTotal() { return total; }
    public double calculateTax(double rate) { return total * rate; }
}
'@

Write-Utf8NoBom 'src\OrderService.java' @'
package demo;

import java.util.HashMap;
import java.util.Map;

public class OrderService {
    private final Map<String, Order> orders = new HashMap<>();

    public void addOrder(Order order) { orders.put(order.getId(), order); }
    public Order findOrder(String orderId) { return orders.get(orderId); }
    public boolean cancelOrder(String orderId) {
        return orders.remove(orderId) != null;
    }
}
'@

git -C $demo init
git -C $demo config user.name 'DocGuard Demo'
git -C $demo config user.email 'docguard-demo@example.invalid'
git -C $demo add README.md docs/API.md src/Order.java src/OrderService.java
git -C $demo commit -m "test: initialize disposable demo repository"

$service = Join-Path $demo 'src\OrderService.java'
$source = [System.IO.File]::ReadAllText($service)
if (-not $source.Contains('return orders.get(orderId);')) {
    throw 'Expected method body was not found.'
}
[System.IO.File]::WriteAllText(
    $service,
    $source.Replace('return orders.get(orderId);', 'return orders.get(orderId.trim());'),
    [System.Text.UTF8Encoding]::new($false)
)

Write-Output "Demo repository: $demo"
```

Use the printed absolute path in DocGuard. Capture the hashes of `src\Order.java`, `src\OrderService.java`, `README.md`, and `docs\API.md` before approving a preview.

## Demonstration sequence

1. Open the dashboard, then **Repository Analysis**. Paste the printed repository path and explicitly run **Analyze repository**.
2. Verify Java files, classes, methods, and coverage findings from the backend.
3. Open **Documentation Drift**. Run **Analyze documentation**, then separately run **Check working-tree drift**. The second action should report the changed `OrderService.findOrder` implementation.
4. Open **RAG Index**. Select **Index Documentation** and verify the backend-reported indexed/skipped/removed document and chunk counts. Select **Check Index Status** for the read-only, repository-scoped counts.
5. Open **AI Documentation**. Choose `docs/API.md`, optionally set a positive maximum method count, and explicitly select **Generate preview**. Review the backend status, warnings, hashes, RAG retrieval/fallback summary, generated Markdown, and generation ID.
6. Use **Retrieve preview** with the generation ID to confirm the persisted record belongs to the selected repository and is still pending.
7. Select **Approve update**, verify the repository, target, and generation ID in the confirmation dialog, then select **Confirm approval**. Approval changes the selected disposable repository’s target Markdown file.
8. Reopen **Repository Analysis** or **Documentation Drift** and explicitly run a fresh full analysis. Compare the backend-reported coverage counts and per-method statuses with the pre-approval results.
9. Verify the source files and README hashes are unchanged and inspect `git diff -- docs/API.md` in the disposable repository.

Do not approve or reject a generation created for another repository. To demonstrate rejection or stale-source/target handling, use separate fresh temporary repositories; rejection should not change Markdown, and stale hashes should block approval.

## Expected results and known limitations

- The sample is expected to contain two Java files, two classes, and six methods. Its initial API document covers only part of the code, so missing documentation is expected.
- A Git working-tree comparison should report the `findOrder` implementation change independently of coverage analysis.
- RAG results and status must identify the selected repository. The backend currently does not persist a last-indexed timestamp, so the page reports that it was not provided.
- In the verified Phase 4F run, RAG indexed two Markdown files and three chunks. Those numbers depend on the fixture and chunker.
- The verified local-model generation was partial because the selected method limit was reached; it returned a persisted pending ID and used repository-scoped retrieved context. Inspect the result from your own run rather than assuming it will be identical.
- In the earlier Phase 4F run, approval changed only `docs/API.md`, but reanalysis stayed at 1/6 documented methods: the generated overview contained package-qualified class headings that approval used for insertion while coverage did not recognize the package. Coverage now recognizes those headings, and new model-generated overview and description headings are rendered as bold labels to avoid creating accidental class sections.
- Method coverage requires a unique class section and a matching method heading. Signatures can include parameter names; bare method headings are accepted only for non-overloaded methods. Duplicate or otherwise ambiguous mappings are not counted. Approval of a partial preview can increase coverage only for the methods actually generated and recognized; it does not imply complete coverage. Previously approved Markdown is not automatically rewritten.
- Generated previews are plain text and are not rendered as HTML. Approval is hash-checked and applies only to the backend-verified repository and target.

## Automated checks

From `backend`, run the configured test suite with the same project-level interpreter:

```powershell
& 'D:\vs codes\Capstone project\venv\Scripts\python.exe' -m pytest tests/test_documentation_approval.py -q
& 'D:\vs codes\Capstone project\venv\Scripts\python.exe' -m pytest tests/test_repository_scoped_rag.py -q
& 'D:\vs codes\Capstone project\venv\Scripts\python.exe' -m pytest -q
```

From `frontend`, run:

```powershell
npx tsc --noEmit
npm run lint
npm run test:run
npm run build
```

## Troubleshooting

- **Backend unavailable:** check that FastAPI is listening on `127.0.0.1:8000` and that the frontend uses `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`.
- **Missing Python imports:** run tests with `D:\vs codes\Capstone project\venv\Scripts\python.exe`, not whichever `python` happens to resolve first in the terminal.
- **Invalid repository:** provide an existing absolute local path; the backend reads local files, while the browser cannot browse them.
- **Groq connection/model error:** verify the backend key, network connectivity, account access, and `GROQ_MODEL`. Never put the key in the frontend.
- **Partial generation:** inspect the backend-reported warnings and errors, and lower the method limit if generation takes too long. A partial preview still requires careful review.
- **No RAG matches:** inspect the repository-scoped status and the generation’s reported retrieval or fallback summary. The status route does not expose internal ChromaDB collections.
- **Stale approval conflict:** regenerate a preview after changing the source or target; do not retry an uncertain approval automatically. Refresh the persisted status first.
