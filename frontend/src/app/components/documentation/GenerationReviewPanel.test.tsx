import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GenerationReviewPanel from "./GenerationReviewPanel";
import {
  approveGeneration,
  getGeneration,
  rejectGeneration,
} from "@/lib/api";
import type { ApprovalResponse, GenerationRecord } from "@/types/api";

vi.mock("@/lib/api", () => ({
  approveGeneration: vi.fn(),
  getApiErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "Backend error",
  getGeneration: vi.fn(),
  rejectGeneration: vi.fn(),
}));

const generationId = "review-generation";
const repositoryPath = String.raw`D:\DocGuard\review-fixture`;
const repositoryIdentity = "c".repeat(64);

function record(
  overrides: Partial<GenerationRecord> = {}
): GenerationRecord {
  return {
    generation_id: generationId,
    repository: "review-fixture",
    repository_identity: repositoryIdentity,
    documentation_target: "docs/API.md",
    generated_markdown: "# Proposed API update",
    generated_classes: [],
    generated_methods: [],
    repository_overview: null,
    ambiguous_documentation_mappings: [],
    generation_status: "complete",
    created_at: "2026-11-07T10:00:00Z",
    source_hashes: { "src/A.java": "source-hash" },
    target_hash_before: "target-hash",
    status: "pending",
    ...overrides,
  };
}

function renderPanel(initialRecord = record()) {
  return render(
    <GenerationReviewPanel
      initialRecord={initialRecord}
      repositoryPath={repositoryPath}
      generatedMarkdown={initialRecord.generated_markdown}
      verifyRepositoryIdentity={vi.fn().mockResolvedValue(repositoryIdentity)}
      onRecordUpdated={vi.fn()}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getGeneration).mockResolvedValue(record());
});

describe("developer review controls", () => {
  it("requires a fresh record and separate confirmation before approval", async () => {
    const user = userEvent.setup();
    vi.mocked(getGeneration)
      .mockResolvedValueOnce(record())
      .mockResolvedValueOnce(record())
      .mockResolvedValueOnce(
        record({
          status: "approved",
          audit: {
            event_type: "approval",
            generation_id: generationId,
            repository: "review-fixture",
            repository_identity: repositoryIdentity,
            documentation_target: "docs/API.md",
            status: "approved",
            timestamp: "2026-11-07T10:00:00Z",
            source_hashes: {},
            documentation_hash_before: "before",
            documentation_hash_after: "after",
            generated_classes: [],
            generated_methods: [],
            failure_reason: null,
          },
        })
      );
    vi.mocked(approveGeneration).mockResolvedValue({
      generation_id: generationId,
      status: "approved",
      documentation_target: "docs/API.md",
    } satisfies ApprovalResponse);
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Approve update" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(
      "Approval may modify the target Markdown file."
    );
    expect(approveGeneration).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(approveGeneration).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Approve update" }));
    await screen.findByRole("dialog");
    expect(approveGeneration).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    expect(
      await screen.findByText("Approval status verified")
    ).toBeInTheDocument();
    expect(approveGeneration).toHaveBeenCalledOnce();
    expect(approveGeneration).toHaveBeenCalledWith(generationId, {
      decision: "approve",
    });
    expect(
      await screen.findByText(/target file content changed/)
    ).toBeInTheDocument();
  });

  it("requires explicit rejection confirmation and refreshes the terminal status", async () => {
    const user = userEvent.setup();
    vi.mocked(getGeneration)
      .mockResolvedValueOnce(record())
      .mockResolvedValueOnce(
        record({
          status: "rejected",
          audit: {
            event_type: "rejection",
            generation_id: generationId,
            repository: "review-fixture",
            repository_identity: repositoryIdentity,
            documentation_target: "docs/API.md",
            status: "rejected",
            timestamp: "2026-11-07T10:00:00Z",
            source_hashes: {},
            documentation_hash_before: "before",
            documentation_hash_after: "before",
            generated_classes: [],
            generated_methods: [],
            failure_reason: null,
          },
        })
      );
    vi.mocked(rejectGeneration).mockResolvedValue({
      generation_id: generationId,
      status: "rejected",
      documentation_target: "docs/API.md",
    });
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Reject preview" }));
    await screen.findByRole("dialog");
    expect(rejectGeneration).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm rejection" }));

    expect(
      await screen.findByText("Rejection status verified")
    ).toBeInTheDocument();
    expect(rejectGeneration).toHaveBeenCalledOnce();
    expect(rejectGeneration).toHaveBeenCalledWith(generationId, {
      decision: "reject",
    });
    expect(
      screen.getByText(/rejection does not modify documentation files/)
    ).toBeInTheDocument();
  });

  it("blocks actions when the persisted record has a different repository identity", async () => {
    const user = userEvent.setup();
    vi.mocked(getGeneration).mockResolvedValue(
      record({ repository_identity: "d".repeat(64) })
    );
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Approve update" }));

    expect(
      await screen.findByText(/different repository identity/)
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(approveGeneration).not.toHaveBeenCalled();
  });

  it("does not retry after an uncertain network outcome and allows read-only status refresh", async () => {
    const user = userEvent.setup();
    vi.mocked(getGeneration).mockResolvedValue(record());
    vi.mocked(approveGeneration).mockRejectedValue(
      new Error("Connection timed out")
    );
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Approve update" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    expect(
      await screen.findByText("Action outcome is not yet confirmed")
    ).toBeInTheDocument();
    const refresh = screen.getByRole("button", {
      name: "Refresh status before any further action",
    });
    expect(refresh).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve update" })).toBeDisabled();
    expect(approveGeneration).toHaveBeenCalledOnce();

    await user.click(refresh);
    expect(await screen.findByText("Persisted status refreshed")).toBeInTheDocument();
    await waitFor(() => expect(getGeneration).toHaveBeenCalledTimes(3));
    expect(approveGeneration).toHaveBeenCalledOnce();
  });

  it("reports stale conflicts from the refreshed persisted record", async () => {
    const user = userEvent.setup();
    vi.mocked(getGeneration)
      .mockResolvedValueOnce(record())
      .mockResolvedValueOnce(record({ status: "stale", failure_reason: "Source changed." }));
    vi.mocked(approveGeneration).mockRejectedValue(
      new Error("409 Conflict")
    );
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Approve update" }));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Confirm approval" }));

    expect(
      await screen.findByText("Preview is stale; approval was blocked")
    ).toBeInTheDocument();
    expect(screen.getAllByText("Source changed.")).not.toHaveLength(0);
    expect(rejectGeneration).not.toHaveBeenCalled();
  });

  it("prevents approval if persisted generated Markdown is empty", async () => {
    renderPanel(record({ generated_markdown: "" }));

    expect(screen.getByRole("button", { name: "Approve update" })).toBeDisabled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(approveGeneration).not.toHaveBeenCalled();
  });
});
