import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Dashboard from "./page";
import { checkBackendHealth } from "@/lib/api";
import { RepositoryHarness } from "@/test/repositoryHarness";

vi.mock("@/lib/api", () => ({
  checkBackendHealth: vi.fn(),
  getApiErrorMessage: () => "Unavailable",
}));

describe("dashboard", () => {
  beforeEach(() => {
    vi.mocked(checkBackendHealth).mockResolvedValue({ message: "ok" });
  });
  it("offers repository selection before analysis", async () => {
    render(<RepositoryHarness repositoryPath=""><Dashboard /></RepositoryHarness>);
    expect(screen.getByRole("link", { name: "Select repository" })).toHaveAttribute("href", "/repository");
    expect(await screen.findByText("Backend: Connected")).toBeInTheDocument();
  });
  it("offers analysis when a repository is selected", async () => {
    render(<RepositoryHarness repositoryPath={String.raw`D:\Repo`}><Dashboard /></RepositoryHarness>);
    expect(await screen.findByRole("link", { name: "Analyze repository" })).toHaveAttribute("href", "/analysis");
  });
});
