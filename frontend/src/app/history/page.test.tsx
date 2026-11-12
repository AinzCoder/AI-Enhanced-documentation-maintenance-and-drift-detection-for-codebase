import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HistoryPage from "./page";
import { apiClient } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
  getApiErrorMessage: () => "Could not load history.",
}));

describe("decision history", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { history: [
      { decision: "approved", repository_path: "D:\\Legacy", documentation_file: "API.md", class_name: "A", method_name: "run" },
      { event_type: "documentation_generation", status: "approved", repository: "New repo", documentation_target: "docs/API.md", generation_id: "abc123" },
    ] } });
  });
  it("renders legacy and generation audit records", async () => {
    render(<HistoryPage />);
    expect(await screen.findByText("New repo")).toBeInTheDocument();
    expect(screen.getByText("Generation ID: abc123")).toBeInTheDocument();
    expect(screen.getByText("A.run")).toBeInTheDocument();
    expect(screen.getByText("Decisions across all repositories.")).toBeInTheDocument();
  });
});
