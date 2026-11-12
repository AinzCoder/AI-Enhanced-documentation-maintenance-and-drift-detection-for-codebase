import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

it("uses the configured public backend URL", async () => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", " https://backend.example.test ");
  const { apiBaseUrl } = await import("./apiBaseUrl");
  expect(apiBaseUrl).toBe("https://backend.example.test");
});

it("defaults to the local backend", async () => {
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
  const { apiBaseUrl } = await import("./apiBaseUrl");
  expect(apiBaseUrl).toBe("http://127.0.0.1:8000");
});
