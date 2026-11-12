import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { signIn, signOut } from "next-auth/react";
import AuthControls from "./AuthControls";

vi.mock("next-auth/react", () => ({ signIn: vi.fn(), signOut: vi.fn() }));

it("offers sign-in to unauthenticated users", async () => {
  render(<AuthControls />);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(signIn).toHaveBeenCalledWith("oidc", { callbackUrl: "/" });
});

it("displays the profile and signs out", async () => {
  render(<AuthControls name="Example User" />);
  expect(screen.getByText("Signed in as Example User")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(signOut).toHaveBeenCalledWith({ callbackUrl: "/" });
});

it("offers recovery for expired sessions", () => {
  render(<AuthControls expired />);
  expect(screen.getByText(/session has expired/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
});
