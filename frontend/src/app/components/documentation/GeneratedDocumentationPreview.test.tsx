import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import GeneratedDocumentationPreview from "./GeneratedDocumentationPreview";

describe("generated documentation preview", () => {
  it("keeps Markdown as text, supports raw view, and copies the original content", async () => {
    const user = userEvent.setup();
    const markdown = "# Preview\n\n<script>alert('unsafe')</script>";
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    const { container } = render(
      <GeneratedDocumentationPreview markdown={markdown} partial />
    );

    expect(container.querySelector("pre")?.textContent).toBe(markdown);
    expect(
      screen.getByText(/This is a partial result/)
    ).toBeInTheDocument();
    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(screen.getByText(/characters/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Raw Markdown" }));
    expect(screen.getByLabelText("Raw generated Markdown")).toHaveValue(markdown);

    await user.click(screen.getByRole("button", { name: "Copy Markdown" }));
    expect(writeText).toHaveBeenCalledWith(markdown);
    expect(await screen.findByText("Markdown copied to clipboard.")).toBeInTheDocument();
  });
});
