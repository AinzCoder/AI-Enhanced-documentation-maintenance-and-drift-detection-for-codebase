// @vitest-environment node
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SignJWT } from "jose";
import { authOptions } from "./auth";

beforeEach(() => {
  vi.stubEnv("OIDC_ISSUER", "https://id.example.test");
  vi.stubEnv("OIDC_CLIENT_ID", "docguard-client");
  vi.stubEnv("OIDC_CLIENT_SECRET", "test-secret");
  vi.stubEnv("OIDC_API_AUDIENCE", "docguard-api");
  vi.stubEnv("OIDC_AUDIENCE_PARAMETER", "audience");
  vi.stubEnv("NEXTAUTH_URL", "https://app.example.test");
  vi.stubEnv("NEXTAUTH_SECRET", "secret-that-is-long-enough-for-the-test-session");
});
afterEach(() => vi.unstubAllEnvs());

async function accessToken(audience: string) {
  return new SignJWT({}).setProtectedHeader({ alg: "HS256" })
    .setIssuer("https://id.example.test").setAudience(audience)
    .setSubject("alice").setExpirationTime("10m")
    .sign(new TextEncoder().encode("test-only-signing-key"));
}

it("configures OIDC discovery, PKCE, state and nonce", () => {
  const provider = authOptions().providers[0];
  expect(provider.type).toBe("oauth");
  if (provider.type !== "oauth") throw new Error("Unexpected provider type");
  expect(provider.checks).toEqual(["pkce", "state", "nonce"]);
  expect(provider.wellKnown).toBe("https://id.example.test/.well-known/openid-configuration");
  expect(provider.authorization).toMatchObject({ params: { audience: "docguard-api" } });
});

it("stores only an audience-matched access token and never exposes it to the session", async () => {
  const callbacks = authOptions().callbacks;
  if (!callbacks?.jwt || !callbacks.session) throw new Error("Missing auth callbacks");
  const callback = callbacks.jwt;
  const token = await callback({
    token: {},
    user: { id: "alice" },
    account: {
      provider: "oidc", providerAccountId: "alice", type: "oauth",
      access_token: await accessToken("docguard-api"),
      id_token: "id-token",
      expires_at: Math.floor(Date.now() / 1000) + 600,
    },
  });
  expect(token.apiAccessToken).toBeTruthy();
  const session = await callbacks.session({ session: { user: { name: "Alice" }, expires: new Date().toISOString() }, token, user: { id: "alice", email: "alice@example.test", emailVerified: null }, newSession: null, trigger: "update" });
  expect(session).toMatchObject({ apiSessionValid: true });
  expect(JSON.stringify(session)).not.toContain(token.apiAccessToken);

  const wrongAudience = await callback({
    token: {}, user: { id: "alice" },
    account: { provider: "oidc", providerAccountId: "alice", type: "oauth",
      access_token: await accessToken("other"), expires_at: Math.floor(Date.now() / 1000) + 600 },
  });
  expect(wrongAudience.apiAccessToken).toBeUndefined();
  const idToken = await accessToken("docguard-api");
  const substituted = await callback({
    token: {}, user: { id: "alice" },
    account: { provider: "oidc", providerAccountId: "alice", type: "oauth",
      access_token: idToken, id_token: idToken, expires_at: Math.floor(Date.now() / 1000) + 600 },
  });
  expect(substituted.apiAccessToken).toBeUndefined();
  const expired = await callbacks.session({
    session: { expires: new Date().toISOString() },
    token: { ...token, apiAccessTokenExpires: 1 },
    user: { id: "alice", email: "alice@example.test", emailVerified: null },
    newSession: null,
    trigger: "update",
  });
  expect(expired).toMatchObject({ apiSessionValid: false });
});

it("fails closed when the API audience is the client ID or hosted configuration is missing", () => {
  vi.stubEnv("OIDC_API_AUDIENCE", "docguard-client");
  expect(() => authOptions()).toThrow("configuration");
  vi.stubEnv("OIDC_API_AUDIENCE", "");
  expect(() => authOptions()).toThrow("configuration");
  vi.stubEnv("OIDC_API_AUDIENCE", "docguard-api");
  vi.stubEnv("OIDC_SCOPES", "profile email");
  expect(() => authOptions()).toThrow("configuration");
});
