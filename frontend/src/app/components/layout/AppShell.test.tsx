import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AppShell from "./AppShell";
import { RepositoryHarness } from "@/test/repositoryHarness";

vi.mock("next/navigation", () => ({ usePathname: () => "/drift" }));

describe("workspace navigation", () => {
  it("groups workflows and shows the selected repository", async () => {
    const user = userEvent.setup();
    render(
      <RepositoryHarness repositoryPath={String.raw`D:\Repo`}>
        <AppShell><p>Content</p></AppShell>
      </RepositoryHarness>
    );
    expect(await screen.findByText(String.raw`D:\Repo`, { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Documentation workflow" })).toBeInTheDocument();
    const links = screen.getByRole("navigation", { name: "Analysis sections" });
    expect(links).toHaveTextContent("Coverage & Git drift");
    expect(links).toHaveTextContent("Search index");
    await user.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(screen.getByRole("button", { name: "Close navigation menu" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close navigation menu" }));
    expect(screen.queryByRole("button", { name: "Close navigation menu" })).not.toBeInTheDocument();
  });
});
