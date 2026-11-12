// @vitest-environment node
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";
import { backendProxy } from "./backendProxy";

vi.mock("@/lib/deployment", () => ({ isHosted: true }));
vi.mock("next-auth/jwt", () => ({ getToken: vi.fn() }));

const repositoryId = "a".repeat(32);

function request(path: string, method = "GET", body?: object, origin = "https://app.example.test") {
  return new NextRequest(`https://app.example.test/api/backend${path}`, {
    method,
    headers: { cookie: "session=test", origin, ...(body ? { "content-type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
}

describe("hosted backend proxy", () => {
  beforeEach(() => {
    vi.stubEnv("NEXTAUTH_URL", "https://app.example.test");
    vi.stubEnv("NEXTAUTH_SECRET", "test-secret-with-more-than-thirty-two-characters");
    vi.stubEnv("DOCGUARD_BACKEND_URL", "https://backend.example.test");
    vi.mocked(getToken).mockResolvedValue({
      apiAccessToken: "server-only-access-token",
      apiAccessTokenExpires: Math.floor(Date.now() / 1000) + 60,
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ ok: true })));
  });
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

  it("rejects missing and expired sessions before contacting FastAPI", async () => {
    vi.mocked(getToken).mockResolvedValueOnce(null).mockResolvedValueOnce({
      apiAccessToken: "expired", apiAccessTokenExpires: Math.floor(Date.now() / 1000) - 1,
    });
    expect((await backendProxy(request("/history"), "/history")).status).toBe(401);
    expect((await backendProxy(request("/history"), "/history")).status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends the API access token only to the backend and resolves repository IDs", async () => {
    const response = await backendProxy(request("/analyze/full", "POST", { repository_path: repositoryId }), "/analyze/full");
    expect(response.status).toBe(200);
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("https://backend.example.test/analyze/full");
    expect(options?.headers).toMatchObject({ authorization: "Bearer server-only-access-token" });
    expect(JSON.parse(String(options?.body))).toEqual({ repository_id: repositoryId });
    expect(await response.text()).not.toContain("server-only-access-token");
  });

  it("rejects cross-origin writes, filesystem paths and non-allowlisted routes", async () => {
    expect((await backendProxy(request("/analyze", "POST", {}, "https://evil.example"), "/analyze")).status).toBe(403);
    expect((await backendProxy(request("/analyze", "POST", { repository_path: "C:\\secret" }), "/analyze")).status).toBe(400);
    expect((await backendProxy(request("/repositories", "POST", {}), "/repositories")).status).toBe(404);
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each([401, 403])("propagates backend %i responses", async (status) => {
    vi.mocked(fetch).mockResolvedValueOnce(Response.json({ detail: "Denied" }, { status }));
    expect((await backendProxy(request("/history"), "/history")).status).toBe(status);
  });

  it("maps the RAG status query without forwarding browser credentials", async () => {
    await backendProxy(request(`/rag/status?repository_path=${repositoryId}`), "/rag/status");
    const [url, options] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe(`https://backend.example.test/rag/status?repository_id=${repositoryId}`);
    expect(options?.headers).not.toHaveProperty("cookie");
  });

  it.each(["/analyze", "/rag/index", "/suggest", "/documentation/generate/full"])(
    "translates the selected repository for %s",
    async (path) => {
      const response = await backendProxy(request(path, "POST", { repository_path: repositoryId }), path);
      expect(response.status).toBe(200);
      const [, options] = vi.mocked(fetch).mock.calls[0];
      expect(JSON.parse(String(options?.body))).toEqual({ repository_id: repositoryId });
    },
  );

  it.each(["/repositories/import/github", "/repositories/import/zip"])(
    "does not forward unavailable import route %s",
    async (path) => {
      expect((await backendProxy(request(path, "POST", {}), path)).status).toBe(404);
      expect(fetch).not.toHaveBeenCalled();
    },
  );
});
