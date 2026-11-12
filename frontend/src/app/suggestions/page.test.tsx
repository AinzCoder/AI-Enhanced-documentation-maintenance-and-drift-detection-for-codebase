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
