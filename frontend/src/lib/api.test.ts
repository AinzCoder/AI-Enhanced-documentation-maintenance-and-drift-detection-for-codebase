import { AxiosError, AxiosHeaders } from "axios";
import { expect, it } from "vitest";
import { getApiErrorMessage } from "./api";

it.each([
  [401, "Your session has expired. Sign in again."],
  [403, "You do not have permission to perform this action."],
])("distinguishes API status %i", (status, message) => {
  const error = new AxiosError("failed", undefined, undefined, undefined, {
    status, statusText: "error", data: { detail: "Denied" },
    headers: {}, config: { headers: new AxiosHeaders() },
  });

  expect(getApiErrorMessage(error)).toBe(message);
});

it("provides actionable local guidance for a missing backend mode", () => {
  const error = new AxiosError("failed", undefined, undefined, undefined, {
    status: 503, statusText: "error", data: { detail: "DocGuard mode is not configured." },
    headers: {}, config: { headers: new AxiosHeaders() },
  });
  expect(getApiErrorMessage(error)).toContain("DOCGUARD_MODE=local");
});
