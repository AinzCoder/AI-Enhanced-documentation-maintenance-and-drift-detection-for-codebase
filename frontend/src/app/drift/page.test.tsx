import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DocumentationDriftPage from "./page";
import { analyzeFullRepository, analyzeRepository } from "@/lib/api";
import { RepositoryHarness } from "@/test/repositoryHarness";
import type { AnalyzeResponse, FullAnalyzeResponse } from "@/types/api";

vi.mock("@/lib/api", () => ({
  analyzeFullRepository: vi.fn(),
  analyzeRepository: vi.fn(),
  getApiErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "Backend error",
}));

const pathA = String.raw`D:\DocGuard\drift-a`;
const pathB = String.raw`D:\DocGuard\drift-b`;

function coverageResponse(): FullAnalyzeResponse {
  return {
    repository: "drift-a",
    analysis_mode: "full",
    summary: {
      java_file_count: 1,
      files_analyzed: 1,
      files_with_errors: 0,
      class_count: 2,
      method_count: 2,
      total_java_source_lines: 9,
      line_count_unavailable: 0,
    },
    files: [],
    documentation_files: ["docs/Empty.md"],
    documentation_analysis: {
      summary: {
        java_file_count: 1,
        class_count: 2,
        method_count: 2,
        documented_class_count: 0,
        missing_class_count: 1,
        ambiguous_class_count: 1,
        unsupported_class_count: 0,
        documented_method_count: 0,
        missing_method_count: 1,
        ambiguous_method_count: 0,
        unsupported_method_count: 1,
        documentation_file_count: 1,
        empty_documentation_file_count: 1,
      },
      classes: [
        {
          source_file: "src/OrderService.java",
          class: "OrderService",
          coverage: "missing",
          methods: [
            {
              method: "createOrder",
              signature: "createOrder()",
              coverage: "missing",
            },
            {
              method: "ambiguousMethod",
              signature: "ambiguousMethod()",
              coverage: "ambiguous",
            },
            {
              method: "unsupportedMethod",
              signature: "unsupportedMethod()",
              coverage: "unsupported",
            },
          ],
        },
      ],
      covered_classes: [],
      covered_methods: [],
      missing_documentation_findings: [
        {
          finding_type: "missing_method",
          source_file: "src/OrderService.java",
          class: "OrderService",
          method: "createOrder",
          signature: "createOrder()",
          reason: "No documentation was found.",
        },
      ],
      empty_documentation_findings: [
        {
          finding_type: "empty_documentation_file",
          documentation_file: "docs/Empty.md",
          reason: "The file contains no documentation text.",
        },
      ],
      ambiguous_mappings: [
        {
          finding_type: "ambiguous_method_mapping",
          source_file: "src/OrderService.java",
          class: "OrderService",
          method: "ambiguousMethod",
        },
      ],
      proposed_documentation_targets: ["docs/API.md"],
      findings: [
        {
          finding_type: "unsupported_method_mapping",
          source_file: "src/OrderService.java",
          class: "OrderService",
          method: "unsupportedMethod",
        },
      ],
      errors: [],
    },
    errors: [],
  };
}

const changedFile: AnalyzeResponse = {
  repository: "drift-a",
  current_commit: "commit-new",
  previous_commit: "commit-old",
  mode: "working_tree",
  results: [
    {
      file: "src/OrderService.java",
      changes: [
        {
          type: "method_body_changed",
          class: "OrderService",
          method: "createOrder",
        },
      ],
      documentation_files: ["docs/Empty.md"],
      drift: [
        {
          type: "documentation_drift",
          class: "OrderService",
          method: "createOrder",
          reason: "The implementation changed.",
        },
      ],
      change_type: "modified",
      git_change_type: "modified",
      old_file: "src/OrderService.java",
      new_file: "src/OrderService.java",
    },
  ],
};

function renderDrift(path = pathA, nextPath?: string) {
  return render(
    <RepositoryHarness
      repositoryPath={path}
      nextRepositoryPath={nextPath}
    >
      <DocumentationDriftPage />
    </RepositoryHarness>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("documentation coverage and drift", () => {
  it("does not analyze on navigation and renders backend coverage, empty, ambiguous, and unsupported findings", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(coverageResponse());
    renderDrift();

    await screen.findByText(pathA);
    expect(analyzeFullRepository).not.toHaveBeenCalled();
    expect(analyzeRepository).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: "Analyze documentation" })
    );

    expect(
      await screen.findByRole("heading", { name: "Missing documentation" })
    ).toBeInTheDocument();
    expect(screen.getByText("Empty")).toBeInTheDocument();
    expect(screen.getAllByText("0%")).toHaveLength(2);
    expect(screen.getByText(/ambiguousMethod/)).toBeInTheDocument();
    expect(screen.getByText(/unsupportedMethod/)).toBeInTheDocument();
    expect(analyzeFullRepository).toHaveBeenCalledWith(pathA);
    expect(analyzeRepository).not.toHaveBeenCalled();
  });

  it("filters missing findings by file, class, or method", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(coverageResponse());
    renderDrift();
    await screen.findByText(pathA);
    await user.click(
      screen.getByRole("button", { name: "Analyze documentation" })
    );
    expect(await screen.findByText(/backend-reported finding/)).toHaveTextContent(
      "1 backend-reported finding"
    );

    await user.type(
      screen.getByRole("searchbox", {
        name: "Search findings by file, class, or method",
      }),
      "missing-value"
    );
    expect(screen.getByText("No findings match these filters.")).toBeInTheDocument();
  });

  it("runs Git-based drift separately from coverage", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(coverageResponse());
    vi.mocked(analyzeRepository).mockResolvedValue(changedFile);
    renderDrift();
    await screen.findByText(pathA);
    await user.click(
      screen.getByRole("button", { name: "Analyze documentation" })
    );
    await screen.findByRole("heading", { name: "Missing documentation" });

    await user.click(
      screen.getByRole("button", { name: "Check working-tree drift" })
    );

    await waitFor(() =>
      expect(analyzeRepository).toHaveBeenCalledWith({
        repository_path: pathA,
        mode: "working_tree",
      })
    );
    expect(await screen.findByText("The implementation changed.")).toBeInTheDocument();
    expect(analyzeFullRepository).toHaveBeenCalledTimes(1);
  });

  it("fetches fresh coverage on explicit reanalysis and recomputes percentages", async () => {
    const user = userEvent.setup();
    const before = coverageResponse();
    const after = coverageResponse();
    before.documentation_analysis.summary.method_count = 6;
    before.documentation_analysis.summary.documented_method_count = 1;
    after.documentation_analysis.summary.method_count = 6;
    after.documentation_analysis.summary.documented_method_count = 2;
    vi.mocked(analyzeFullRepository)
      .mockResolvedValueOnce(before)
      .mockResolvedValueOnce(after);
    renderDrift();

    await user.click(screen.getByRole("button", { name: "Analyze documentation" }));
    await waitFor(() =>
      expect(screen.getByRole("progressbar", { name: "Method coverage" }))
        .toHaveAttribute("aria-valuenow", "17")
    );
    await user.click(screen.getByRole("button", { name: "Analyze documentation" }));
    await waitFor(() =>
      expect(screen.getByRole("progressbar", { name: "Method coverage" }))
        .toHaveAttribute("aria-valuenow", "33")
    );
    expect(analyzeFullRepository).toHaveBeenCalledTimes(2);
    expect(analyzeRepository).not.toHaveBeenCalled();
  });

  it("clears coverage and drift when the shared repository changes", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(coverageResponse());
    renderDrift(pathA, pathB);
    await screen.findByText(pathA);
    await user.click(
      screen.getByRole("button", { name: "Analyze documentation" })
    );
    await screen.findByRole("heading", { name: "Missing documentation" });

    await user.click(screen.getByRole("button", { name: "Switch repository" }));

    expect(await screen.findByText(pathB)).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Missing documentation" })
    ).not.toBeInTheDocument();
    expect(screen.queryByText("createOrder")).not.toBeInTheDocument();
  });
});
