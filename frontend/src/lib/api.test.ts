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
