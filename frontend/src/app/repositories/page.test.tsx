import { render, screen, waitFor } from "@testing-library/react";
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

  it("switches sources without sending unavailable GitHub imports", async () => {
    const user = userEvent.setup();
    render(<RepositoryHarness repositoryPath=""><RepositoriesPage /></RepositoryHarness>);
    await screen.findByRole("link", { name: "Analyze" });
    expect(screen.getByLabelText("Repository path")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "GitHub Repository URL" }));
    expect(screen.queryByLabelText("Repository path")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("GitHub repository URL"), "https://github.com/example/project");
    expect(screen.getByText("URL format is valid.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import from GitHub" })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
    await user.click(screen.getByRole("radio", { name: "Local Repository Path" }));
    expect(screen.getByLabelText("Repository path")).toBeInTheDocument();
  });

  it("registers an existing Windows path and prevents duplicate requests", async () => {
    const user = userEvent.setup();
    let finish!: (value: { data: { status: string; message: string } }) => void;
    vi.mocked(axios.post).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    render(<RepositoryHarness repositoryPath=""><RepositoriesPage /></RepositoryHarness>);
    await screen.findByRole("link", { name: "Analyze" });
    await user.type(screen.getByLabelText("Repository path"), String.raw`D:\Example`);
    await user.click(screen.getByRole("button", { name: "Add Repository" }));
    expect(screen.getByRole("button", { name: /Registering/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Registering/ }));
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith("https://backend.example.test/repositories", { repository_path: String.raw`D:\Example` });
    finish({ data: { status: "success", message: "Repository registered successfully." } });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Repository registered successfully."));
  });

  it("reports missing paths and registration failures", async () => {
    const user = userEvent.setup();
    vi.mocked(axios.post).mockResolvedValueOnce({ data: { status: "error", message: "Repository not found." } });
    render(<RepositoryHarness repositoryPath=""><RepositoriesPage /></RepositoryHarness>);
    await screen.findByRole("link", { name: "Analyze" });
    await user.click(screen.getByRole("button", { name: "Add Repository" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Please enter a repository path.");
    expect(axios.post).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Repository path"), String.raw`D:\missing`);
    await user.click(screen.getByRole("button", { name: "Add Repository" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Repository not found.");
  });
});
