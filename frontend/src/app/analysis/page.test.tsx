import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RepositoryAnalysisPage from "./page";
import { analyzeFullRepository, analyzeRepository } from "@/lib/api";
import { RepositoryHarness } from "@/test/repositoryHarness";
import type { AnalyzeResponse, FullAnalyzeResponse } from "@/types/api";

vi.mock("@/lib/api", () => ({
  analyzeFullRepository: vi.fn(),
  analyzeRepository: vi.fn(),
  getApiErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "Backend error",
}));

const repositoryPath = String.raw`D:\DocGuard\analysis-fixture`;

function fullAnalysis(
  overrides: Partial<FullAnalyzeResponse> = {}
): FullAnalyzeResponse {
  return {
    repository: "analysis-fixture",
    analysis_mode: "full",
    summary: {
      java_file_count: 1,
      files_analyzed: 1,
      files_with_errors: 0,
      class_count: 1,
      method_count: 2,
      total_java_source_lines: 8,
      line_count_unavailable: 0,
    },
    files: [
      {
        file: "src/OrderService.java",
        package: "demo",
        line_count: 8,
        class_count: 1,
        method_count: 2,
        classes: [
          {
            name: "OrderService",
            comment: null,
            method_count: 2,
            methods: [],
          },
        ],
      },
    ],
    documentation_files: ["docs/API.md"],
    documentation_analysis: {
      summary: {
        java_file_count: 1,
        class_count: 1,
        method_count: 2,
        documented_class_count: 0,
        missing_class_count: 1,
        ambiguous_class_count: 0,
        unsupported_class_count: 0,
        documented_method_count: 0,
        missing_method_count: 2,
        ambiguous_method_count: 0,
        unsupported_method_count: 0,
        documentation_file_count: 1,
        empty_documentation_file_count: 0,
      },
      classes: [],
      covered_classes: [],
      covered_methods: [],
      missing_documentation_findings: [],
      empty_documentation_findings: [],
      ambiguous_mappings: [],
      proposed_documentation_targets: [],
      findings: [],
      errors: [],
    },
    errors: [],
    ...overrides,
  };
}

function gitAnalysis(mode: "working_tree" | "commits"): AnalyzeResponse {
  return {
    repository: "analysis-fixture",
    current_commit: "new-commit",
    previous_commit: "base-commit",
    mode,
    results: [],
  };
}

function renderAnalysis(path = repositoryPath, nextRepositoryPath?: string) {
  return render(
    <RepositoryHarness
      repositoryPath={path}
      nextRepositoryPath={nextRepositoryPath}
    >
      <RepositoryAnalysisPage />
    </RepositoryHarness>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("repository analysis page", () => {
  it("does not analyze on navigation and sends full analysis only after submit", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(fullAnalysis());
    renderAnalysis();

    await screen.findByDisplayValue(repositoryPath);
    expect(analyzeFullRepository).not.toHaveBeenCalled();
    expect(analyzeRepository).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Analyze repository" }));

    expect(await screen.findByText("Java files analyzed")).toBeInTheDocument();
    expect(screen.getByText("Methods detected")).toBeInTheDocument();
    expect(
      screen.getByText(
        /For change-linked drift, open Documentation Drift and run a working-tree comparison\./
      )
    ).toBeInTheDocument();
    expect(analyzeFullRepository).toHaveBeenCalledWith(repositoryPath);
    expect(analyzeRepository).not.toHaveBeenCalled();
  });

  it("sends the selected Git working-tree request separately from full analysis", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeRepository).mockResolvedValue(gitAnalysis("working_tree"));
    renderAnalysis();

    await screen.findByDisplayValue(repositoryPath);
    await user.selectOptions(
      screen.getByLabelText("Analysis mode"),
      "working_tree"
    );
    await user.click(screen.getByRole("button", { name: "Analyze repository" }));

    await waitFor(() =>
      expect(analyzeRepository).toHaveBeenCalledWith({
        repository_path: repositoryPath,
        mode: "working_tree",
      })
    );
    expect(analyzeFullRepository).not.toHaveBeenCalled();
  });

  it("clears the previous repository's results when the path changes", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(fullAnalysis());
    renderAnalysis();
    await screen.findByDisplayValue(repositoryPath);
    await user.click(screen.getByRole("button", { name: "Analyze repository" }));
    expect(await screen.findByText("Java files analyzed")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Local repository path"), "-other");
    expect(screen.queryByText("Java files analyzed")).not.toBeInTheDocument();
    expect(screen.getByText("No analysis results yet")).toBeInTheDocument();
    expect(analyzeFullRepository).toHaveBeenCalledTimes(1);
  });

  it("clears results when the selected repository changes outside the path input", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(fullAnalysis());
    renderAnalysis(repositoryPath, String.raw`D:\DocGuard\another-fixture`);

    await screen.findByDisplayValue(repositoryPath);
    await user.click(screen.getByRole("button", { name: "Analyze repository" }));
    expect(await screen.findByText("Java files analyzed")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Switch repository" }));

    expect(
      await screen.findByText("No analysis results yet")
    ).toBeInTheDocument();
    expect(screen.queryByText("Java files analyzed")).not.toBeInTheDocument();
    expect(analyzeFullRepository).toHaveBeenCalledTimes(1);
  });

  it("sends an optional base commit for commit comparison", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeRepository).mockResolvedValue(gitAnalysis("commits"));
    renderAnalysis();

    await screen.findByDisplayValue(repositoryPath);
    await user.selectOptions(screen.getByLabelText("Analysis mode"), "commits");
    await user.type(screen.getByLabelText("Base commit (optional)"), "abc123");
    await user.click(screen.getByRole("button", { name: "Analyze repository" }));

    await waitFor(() =>
      expect(analyzeRepository).toHaveBeenCalledWith({
        repository_path: repositoryPath,
        mode: "commits",
        base_commit: "abc123",
      })
    );
  });

  it("validates an empty path and handles backend failures visibly", async () => {
    const user = userEvent.setup();
    const { rerender } = renderAnalysis("");
    await user.click(screen.getByRole("button", { name: "Analyze repository" }));

    expect(
      await screen.findByText("Enter a repository path before starting analysis.")
    ).toBeInTheDocument();
    expect(analyzeFullRepository).not.toHaveBeenCalled();

    vi.mocked(analyzeFullRepository).mockRejectedValue(
      new Error("Backend unavailable")
    );
    rerender(
      <RepositoryHarness repositoryPath={repositoryPath}>
        <RepositoryAnalysisPage />
      </RepositoryHarness>
    );
    await screen.findByDisplayValue(repositoryPath);
    await user.click(screen.getByRole("button", { name: "Analyze repository" }));
    expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
  });

  it("renders a successful empty Java scan as empty results", async () => {
    const user = userEvent.setup();
    vi.mocked(analyzeFullRepository).mockResolvedValue(
      fullAnalysis({
        summary: {
          java_file_count: 0,
          files_analyzed: 0,
          files_with_errors: 0,
          class_count: 0,
          method_count: 0,
          total_java_source_lines: 0,
          line_count_unavailable: 0,
        },
        files: [],
        documentation_files: [],
      })
    );
    renderAnalysis();
    await screen.findByDisplayValue(repositoryPath);
    await user.click(screen.getByRole("button", { name: "Analyze repository" }));

    expect(await screen.findByText("No Java files were found.")).toBeInTheDocument();
  });
});
