import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import axios from "axios";
import RepositoriesPage from "./page";
import { RepositoryHarness } from "@/test/repositoryHarness";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";

vi.mock("axios", () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), isAxiosError: vi.fn() } }));
vi.mock("@/lib/apiBaseUrl", () => ({ apiBaseUrl: "https://backend.example.test" }));

function SelectedRepository() {
  const { repositoryPath } = useRepositoryAnalysis();
  return <p>Selected: {repositoryPath}</p>;
}

describe("registered repositories", () => {
  beforeEach(() => {
    vi.mocked(axios.get).mockResolvedValue({
      data: { repositories: [{ id: 1, name: "Example", path: String.raw`D:\Example`, branch: "main" }] },
    });
  });
  it("selects the registered path before opening analysis", async () => {
    const user = userEvent.setup();
    render(<RepositoryHarness repositoryPath=""><SelectedRepository /><RepositoriesPage /></RepositoryHarness>);
    const link = await screen.findByRole("link", { name: "Analyze" });
    expect(axios.get).toHaveBeenCalledWith("https://backend.example.test/repositories");
    expect(link).toHaveAttribute("href", "/analysis");
    link.addEventListener("click", (event) => event.preventDefault(), { once: true });
    await user.click(link);
    expect(screen.getByText(String.raw`Selected: D:\Example`)).toBeInTheDocument();
  });
});
