import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AiDocumentationPage from "./page";
import {
  generateFullDocumentation,
  getGeneration,
} from "@/lib/api";
import { getWindowsRepositoryIdentity } from "@/lib/repositoryIdentity";
import { RepositoryHarness } from "@/test/repositoryHarness";
import type {
  FullDocumentationResponse,
  GenerationRecord,
} from "@/types/api";

vi.mock("@/lib/api", () => ({
  generateFullDocumentation: vi.fn(),
  getApiErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "Backend error",
  getGeneration: vi.fn(),
}));

vi.mock("@/lib/repositoryIdentity", () => ({
  getWindowsRepositoryIdentity: vi.fn(),
}));

const repositoryPath = String.raw`D:\DocGuard\generator-fixture`;
const identity = "a".repeat(64);
const generationId = "generation-123";

function response(
  overrides: Partial<FullDocumentationResponse> = {}
): FullDocumentationResponse {
  return {
    repository: "generator-fixture",
    documentation_target: "docs/API.md",
    generated_markdown: "# Generated preview\n\nA method description.",
    generated_classes: [],
    generated_methods: [],
    skipped_documented_methods: [],
    repository_overview: null,
    errors: [],
    generation_status: "partial",
    source_hashes: { "src/A.java": "source-hash" },
    target_hash_at_generation: "target-hash",
    ambiguous_documentation_mappings: [],
    retrieval: {
      strategy: "repository_scoped_chromadb_with_local_markdown_fallback",
      vector_store_used: false,
      repository_scoped: true,
      fallback_used: true,
      fallback_count: 1,
      query_count: 2,
      retrieved_chunks: 0,
      indexing: {
        indexed_files: 1,
        skipped_files: 0,
        deleted_files: 0,
        indexed_chunks: 1,
        error_count: 0,
      },
      errors: [],
    },
    context_limits: { max_context_characters: 5000 },
    generation_id: generationId,
    approval_status: "pending",
    ...overrides,
  };
}

function record(
  overrides: Partial<GenerationRecord> = {}
): GenerationRecord {
  return {
    generation_id: generationId,
    repository: "generator-fixture",
    repository_identity: identity,
    documentation_target: "docs/API.md",
    generated_markdown: "# Generated preview\n\nA method description.",
    generated_classes: [],
    generated_methods: [],
    repository_overview: null,
    ambiguous_documentation_mappings: [],
    generation_status: "partial",
    created_at: "2026-11-07T10:00:00Z",
    source_hashes: { "src/A.java": "source-hash" },
    target_hash_before: "target-hash",
    status: "pending",
    ...overrides,
  };
}

function renderGenerator(path = repositoryPath, nextPath?: string) {
  return render(
    <RepositoryHarness repositoryPath={path} nextRepositoryPath={nextPath}>
      <AiDocumentationPage />
    </RepositoryHarness>
  );
}

async function prepareGenerationForm(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByText(repositoryPath);
  await user.type(
    screen.getByLabelText("Target Markdown path"),
    "docs/API.md"
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getWindowsRepositoryIdentity).mockImplementation((path) =>
    Promise.resolve(
      path === repositoryPath ? identity : "b".repeat(64)
    )
  );
  vi.mocked(getGeneration).mockResolvedValue(record());
});

describe("AI documentation workflow", () => {
  it("shows an empty state and makes no generation or lookup requests without a repository", () => {
    renderGenerator("");

    expect(
      screen.getByRole("heading", {
        name: "Select a repository to generate documentation",
      })
    ).toBeInTheDocument();
    expect(generateFullDocumentation).not.toHaveBeenCalled();
    expect(getGeneration).not.toHaveBeenCalled();
  });

  it("sends a valid request only after click and displays partial Markdown and RAG fallback", async () => {
    const user = userEvent.setup();
    vi.mocked(generateFullDocumentation).mockResolvedValue(response());
    renderGenerator();
    expect(
      screen.getByText(/Generation sends selected source code and documentation context to Groq/)
    ).toBeInTheDocument();
    await prepareGenerationForm(user);
    await user.type(
      screen.getByLabelText("Maximum missing methods (optional)"),
      "3"
    );

    expect(generateFullDocumentation).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Generate preview" }));

    expect(await screen.findByRole("region", { name: "Developer review" })).toBeInTheDocument();
    expect(generateFullDocumentation).toHaveBeenCalledWith(
      {
        repository_path: repositoryPath,
        target_documentation_file: "docs/API.md",
        include_repository_overview: true,
        max_methods: 3,
      },
      expect.any(AbortSignal)
    );
    expect(
      screen.getByText("This is a partial result. Review the backend-reported warnings and errors before using the preview.")
    ).toBeInTheDocument();
    expect(screen.getByText("Local Markdown fallback used")).toBeInTheDocument();
    expect(screen.getByText("Generated documentation is a preview. Repository documentation is not updated until a developer explicitly approves the change.")).toBeInTheDocument();
  });

  it("rejects traversal targets and non-positive method limits without requests", async () => {
    const user = userEvent.setup();
    renderGenerator();
    await screen.findByText(repositoryPath);
    await user.type(
      screen.getByLabelText("Target Markdown path"),
      "../docs/API.md"
    );
    await user.click(screen.getByRole("button", { name: "Generate preview" }));
    expect(
      await screen.findByText(/cannot contain a '\.\.' path segment/)
    ).toBeInTheDocument();
    expect(generateFullDocumentation).not.toHaveBeenCalled();

    await user.clear(screen.getByLabelText("Target Markdown path"));
    await user.type(
      screen.getByLabelText("Target Markdown path"),
      "docs/API.md"
    );
    await user.type(
      screen.getByLabelText("Maximum missing methods (optional)"),
      "0"
    );
    await user.click(screen.getByRole("button", { name: "Generate preview" }));
    expect(
      await screen.findByText("Maximum methods must be a positive whole number.")
    ).toBeInTheDocument();
    expect(generateFullDocumentation).not.toHaveBeenCalled();
  });

  it("blocks duplicate submissions while generation is pending", async () => {
    const user = userEvent.setup();
    let finishGeneration:
      | ((value: FullDocumentationResponse) => void)
      | undefined;
    vi.mocked(generateFullDocumentation).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishGeneration = resolve;
        })
    );
    renderGenerator();
    await prepareGenerationForm(user);
    await user.click(screen.getByRole("button", { name: "Generate preview" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "requesting Groq generation"
    );
    expect(
      screen.getByRole("button", { name: "Generating preview…" })
    ).toBeDisabled();
    expect(generateFullDocumentation).toHaveBeenCalledOnce();
    finishGeneration?.(response());
    await screen.findByRole("region", { name: "Generated Markdown preview" });
  });

  it("shows the backend's actionable rate-limit message", async () => {
    const user = userEvent.setup();
    sessionStorage.clear();
    const message = "Groq is temporarily rate-limited. Please retry in approximately 35 seconds.";
    vi.mocked(generateFullDocumentation).mockResolvedValue(response({
      generation_id: null,
      approval_status: "unavailable",
      generation_status: "failed",
      generated_markdown: null,
      errors: [{ stage: "method_generation", file: "src/A.java", message }],
    }));
    renderGenerator();
    await prepareGenerationForm(user);
    await user.click(screen.getByRole("button", { name: "Generate preview" }));
    expect((await screen.findAllByText(message)).length).toBeGreaterThan(0);
    expect(getGeneration).not.toHaveBeenCalled();
  });

  it("does not render a successful preview when generation returns empty content", async () => {
    const user = userEvent.setup();
    vi.mocked(generateFullDocumentation).mockResolvedValue(
      response({
        generated_markdown: null,
        generation_status: "failed",
        generation_id: null,
      })
    );
    renderGenerator();
    await prepareGenerationForm(user);
    await user.click(screen.getByRole("button", { name: "Generate preview" }));

    expect(
      await screen.findByText(/did not return usable generated Markdown/)
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Generated Markdown preview" })
    ).not.toBeInTheDocument();
  });

  it("withholds persisted preview content when repository ownership does not match", async () => {
    const user = userEvent.setup();
    vi.mocked(getGeneration).mockResolvedValue(
      record({ repository_identity: "b".repeat(64) })
    );
    renderGenerator();
    await screen.findByText(repositoryPath);
    await user.type(screen.getByLabelText("Generation ID"), generationId);
    await user.click(screen.getByRole("button", { name: "Retrieve preview" }));

    expect(
      await screen.findByText(/different repository identity/)
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Generated Markdown preview" })
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Developer review" })).not.toBeInTheDocument();
  });

  it("aborts an in-flight generation and clears its preview when the repository changes", async () => {
    const user = userEvent.setup();
    let finishGeneration:
      | ((value: FullDocumentationResponse) => void)
      | undefined;
    vi.mocked(generateFullDocumentation).mockImplementation(
      () =>
        new Promise((resolve) => {
          finishGeneration = resolve;
        })
    );
    renderGenerator(repositoryPath, String.raw`D:\DocGuard\other-repository`);
    await prepareGenerationForm(user);
    await user.click(screen.getByRole("button", { name: "Generate preview" }));
    await waitFor(() => expect(generateFullDocumentation).toHaveBeenCalledOnce());
    const signal = vi.mocked(generateFullDocumentation).mock.calls[0][1];

    await user.click(screen.getByRole("button", { name: "Switch repository" }));
    await screen.findAllByText(String.raw`D:\DocGuard\other-repository`);
    finishGeneration?.(response());

    expect(signal?.aborted).toBe(true);
    expect(
      screen.queryByRole("region", { name: "Generated Markdown preview" })
    ).not.toBeInTheDocument();
  });
});
