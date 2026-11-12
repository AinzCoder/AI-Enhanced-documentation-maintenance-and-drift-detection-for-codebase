import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import axios from "axios";
import RepositoriesPage from "./page";
import { RepositoryHarness } from "@/test/repositoryHarness";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";

vi.mock("@/lib/deployment", () => ({ isHosted: true }));
vi.mock("axios", () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), isAxiosError: vi.fn() } }));
vi.mock("@/lib/apiBaseUrl", () => ({ apiBaseUrl: "/api/backend" }));

function Selection() {
  const { repositoryPath } = useRepositoryAnalysis();
  return <p>Selected: {repositoryPath}</p>;
}

it("selects an opaque hosted ID and does not offer filesystem imports", async () => {
  const id = "a".repeat(32);
  vi.mocked(axios.get).mockResolvedValue({ data: { repositories: [{ id, name: "Example" }] } });
  render(<RepositoryHarness repositoryPath=""><Selection /><RepositoriesPage /></RepositoryHarness>);
  const link = await screen.findByRole("link", { name: "Analyze" });
  link.addEventListener("click", (event) => event.preventDefault(), { once: true });
  await userEvent.click(link);
  expect(screen.getByText(`Selected: ${id}`)).toBeInTheDocument();
  expect(screen.queryByLabelText("Repository path")).not.toBeInTheDocument();
  expect(screen.getByText(/imports are not yet available/i)).toBeInTheDocument();
});

it("offers disabled GitHub and ZIP imports without exposing local paths", async () => {
  const user = userEvent.setup();
  vi.mocked(axios.get).mockResolvedValue({ data: { repositories: [] } });
  render(<RepositoryHarness repositoryPath=""><RepositoriesPage /></RepositoryHarness>);
  expect(screen.queryByRole("radio", { name: "Local Repository Path" })).not.toBeInTheDocument();
  await user.type(screen.getByLabelText("GitHub repository URL"), "https://github.com/example/project?x=1");
  expect(screen.getByText(/Enter a public GitHub HTTPS/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Import from GitHub" })).toBeDisabled();
  await user.click(screen.getByRole("radio", { name: "ZIP Upload" }));
  await user.upload(screen.getByLabelText("Repository ZIP file"), new File(["content"], "repo.zip", { type: "application/zip" }));
  expect(screen.getByText(/repo.zip/)).toBeInTheDocument();
  expect(screen.getByText("ZIP file selected.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Upload ZIP" })).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it.each([
  [401, "Your session has expired. Sign in again."],
  [403, "You do not have permission to access these repositories."],
])("reports hosted API error %s", async (status, message) => {
  const error = { response: { status } };
  vi.mocked(axios.get).mockRejectedValueOnce(error);
  vi.mocked(axios.isAxiosError).mockReturnValue(true);
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  render(<RepositoryHarness repositoryPath=""><RepositoriesPage /></RepositoryHarness>);
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  log.mockRestore();
});

it("reports an empty ZIP without enabling upload", async () => {
  const user = userEvent.setup();
  vi.mocked(axios.get).mockResolvedValue({ data: { repositories: [] } });
  render(<RepositoryHarness repositoryPath=""><RepositoriesPage /></RepositoryHarness>);
  await user.click(screen.getByRole("radio", { name: "ZIP Upload" }));
  await user.upload(screen.getByLabelText("Repository ZIP file"), new File([], "empty.zip", { type: "application/zip" }));
  expect(screen.getByText(/empty.zip/)).toBeInTheDocument();
  expect(screen.getByText("The ZIP file is empty.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Upload ZIP" })).toBeDisabled();
});
