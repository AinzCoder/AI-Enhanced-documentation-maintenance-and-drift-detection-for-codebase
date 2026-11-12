import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import axios from "axios";
import SuggestionsPage from "./page";

vi.mock("axios", () => ({ default: { post: vi.fn() } }));
vi.mock("@/lib/apiBaseUrl", () => ({ apiBaseUrl: "https://backend.example.test" }));

it("uses the configured backend and no machine-specific default repository", async () => {
  const user = userEvent.setup();
  vi.mocked(axios.post).mockResolvedValue({ data: { error: "Test response" } });
  render(<SuggestionsPage />);
  expect(screen.getByLabelText("Repository path")).toHaveValue("");
  await user.type(screen.getByLabelText("Repository path"), "D:\\Example");
  await user.type(screen.getByLabelText("Java file path"), "A.java");
  await user.type(screen.getByLabelText("Class name"), "A");
  await user.type(screen.getByLabelText("Method name"), "example");
  await user.selectOptions(screen.getByLabelText("Change type"), "method_added");
  await user.click(screen.getByRole("button", { name: "Generate Suggestion" }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
    "https://backend.example.test/suggest",
    expect.objectContaining({ repository_path: "D:\\Example" }),
  ));
});

it("renders retrieved documentation using the backend metadata fields", async () => {
  const user = userEvent.setup();
  vi.mocked(axios.post).mockResolvedValueOnce({ data: {
    class: "A", method: "example", change_type: "method_added",
    target_documentation: "docs/API.md", suggestion: "Suggested text", developer_comment: null,
    retrieved_documents: [{
      documentation_file: "docs/API.md", chunk_index: 2, source_type: "documentation",
      section_heading: "Overview", content_hash: "hash",
    }],
  } });
  render(<SuggestionsPage />);
  await user.type(screen.getByLabelText("Repository path"), "D:\\Example");
  await user.type(screen.getByLabelText("Java file path"), "A.java");
  await user.type(screen.getByLabelText("Class name"), "A");
  await user.type(screen.getByLabelText("Method name"), "example");
  await user.selectOptions(screen.getByLabelText("Change type"), "method_added");
  await user.click(screen.getByRole("button", { name: "Generate Suggestion" }));
  expect(await screen.findByText("docs/API.md")).toBeInTheDocument();
  expect(screen.getByText("Chunk 2 · documentation · Overview")).toBeInTheDocument();
});
