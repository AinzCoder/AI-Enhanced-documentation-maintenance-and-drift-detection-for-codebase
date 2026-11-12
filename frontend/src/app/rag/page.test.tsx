import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RagIndexPage from "./page";
import { getRagStatus, indexRepository } from "@/lib/api";
import { getWindowsRepositoryIdentity } from "@/lib/repositoryIdentity";
import { RepositoryHarness } from "@/test/repositoryHarness";

vi.mock("@/lib/api", () => ({
  getApiErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "Backend error",
  getRagStatus: vi.fn(),
  indexRepository: vi.fn(),
}));

vi.mock("@/lib/repositoryIdentity", () => ({
  getWindowsRepositoryIdentity: vi.fn(),
}));

const repositoryA = String.raw`D:\DocGuard\repo-a`;
const repositoryB = String.raw`D:\DocGuard\repo-b`;
const identityA = "a".repeat(64);

function renderRag(repositoryPath = repositoryA, nextRepositoryPath?: string) {
  return render(
    <RepositoryHarness
      repositoryPath={repositoryPath}
      nextRepositoryPath={nextRepositoryPath}
    >
      <RagIndexPage />
    </RepositoryHarness>
  );
}

const emptyIndex = {
  repository: "repo-a",
  repository_id: identityA,
  indexed_files: [],
  skipped_files: [],
  deleted_files: [],
  indexed_chunks: 0,
  errors: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getWindowsRepositoryIdentity).mockResolvedValue(identityA);
});

describe("RAG index page", () => {
  it("shows an empty repository-selection state without making requests", () => {
    renderRag("");

    expect(
      screen.getByRole("heading", {
        name: "Select a repository to manage its documentation index",
      })
    ).toBeInTheDocument();
    expect(getRagStatus).not.toHaveBeenCalled();
    expect(indexRepository).not.toHaveBeenCalled();
  });

  it("only indexes after explicit click and displays backend counts and partial errors", async () => {
    const user = userEvent.setup();
    vi.mocked(indexRepository).mockResolvedValue({
      ...emptyIndex,
      indexed_files: ["docs/API.md"],
      skipped_files: ["README.md"],
      deleted_files: ["docs/Old.md"],
      indexed_chunks: 3,
      errors: [
        {
          file: "docs/Broken.md",
          stage: "document_indexing",
          message: "Embedding failed.",
        },
      ],
    });
    renderRag();

    await screen.findByText(repositoryA);
    expect(indexRepository).not.toHaveBeenCalled();
    expect(getRagStatus).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Index Documentation" }));

    expect(await screen.findByText("Completed with errors")).toBeInTheDocument();
    expect(indexRepository).toHaveBeenCalledWith(
      { repository_path: repositoryA },
      expect.any(AbortSignal)
    );
    expect(screen.getByText("Indexed documents")).toBeInTheDocument();
    expect(screen.getByText(/docs\/Broken\.md/)).toBeInTheDocument();
    expect(screen.getByText("Embedding failed.")).toBeInTheDocument();
    expect(getRagStatus).not.toHaveBeenCalled();
  });

  it("performs an explicit read-only status check and withholds mismatched identities", async () => {
    const user = userEvent.setup();
    vi.mocked(getRagStatus).mockResolvedValue({
      repository: "other-repo",
      repository_id: "b".repeat(64),
      index_available: true,
      indexed_document_count: 7,
      chunk_count: 12,
      last_successful_indexing: null,
    });
    renderRag();
    await screen.findByText(repositoryA);

    await user.click(screen.getByRole("button", { name: "Check Index Status" }));

    expect(
      await screen.findByText(/identity did not match the selected repository/)
    ).toBeInTheDocument();
    expect(getRagStatus).toHaveBeenCalledWith(
      repositoryA,
      expect.any(AbortSignal)
    );
    expect(screen.queryByText("12")).not.toBeInTheDocument();
  });

  it("shows verified empty-index status without inventing timestamps", async () => {
    const user = userEvent.setup();
    vi.mocked(getRagStatus).mockResolvedValue({
      repository: "repo-a",
      repository_id: identityA,
      index_available: true,
      indexed_document_count: 0,
      chunk_count: 0,
      last_successful_indexing: null,
    });
    renderRag();
    await screen.findByText(repositoryA);
    await user.click(screen.getByRole("button", { name: "Check Index Status" }));

    expect(await screen.findByText("Not provided by backend")).toBeInTheDocument();
    expect(
      screen.getByText(/index is available but currently contains no documentation/)
    ).toBeInTheDocument();
  });

  it("clears prior repository results and aborts in-flight indexing on switch", async () => {
    const user = userEvent.setup();
    let finishIndex: ((value: typeof emptyIndex) => void) | undefined;
    vi.mocked(indexRepository).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishIndex = resolve;
        })
    );
    const { getByRole } = renderRag(repositoryA, repositoryB);
    await screen.findByText(repositoryA);
    await user.click(screen.getByRole("button", { name: "Index Documentation" }));
    await waitFor(() => expect(indexRepository).toHaveBeenCalledOnce());
    const requestSignal = vi.mocked(indexRepository).mock.calls[0][1];

    await user.click(getByRole("button", { name: "Switch repository" }));
    await screen.findByText(repositoryB);
    finishIndex?.(emptyIndex);

    expect(requestSignal?.aborted).toBe(true);
    expect(screen.queryByRole("heading", { name: "Indexing result" })).not.toBeInTheDocument();
    expect(screen.queryByText(repositoryA)).not.toBeInTheDocument();
  });

  it("reports a missing repository path without calling the backend", async () => {
    const user = userEvent.setup();
    vi.mocked(getWindowsRepositoryIdentity).mockResolvedValue(null);
    renderRag(repositoryA);
    await screen.findByText(repositoryA);
    await user.click(screen.getByRole("button", { name: "Index Documentation" }));

    expect(
      await screen.findByText(/identity could not be calculated/)
    ).toBeInTheDocument();
    expect(indexRepository).not.toHaveBeenCalled();
  });
});
