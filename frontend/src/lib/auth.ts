import type { NextAuthOptions } from "next-auth";
import { decodeJwt } from "jose";

function configuration() {
  const issuer = process.env.OIDC_ISSUER;
  const clientId = process.env.OIDC_CLIENT_ID;
  const clientSecret = process.env.OIDC_CLIENT_SECRET;
  const audience = process.env.OIDC_API_AUDIENCE;
  const parameter = process.env.OIDC_AUDIENCE_PARAMETER;
  const secret = process.env.NEXTAUTH_SECRET;
  const baseUrl = process.env.NEXTAUTH_URL;
  const scopes = process.env.OIDC_SCOPES || "openid profile email";
  if (!issuer || !clientId || !clientSecret || !audience || audience === clientId ||
      !secret || secret.length < 32 || !baseUrl ||
      (parameter !== "audience" && parameter !== "resource") ||
      !scopes.split(/\s+/).includes("openid")) {
    throw new Error("Hosted OIDC configuration is incomplete.");
  }
  const issuerUrl = new URL(issuer);
  const appUrl = new URL(baseUrl);
  if (issuerUrl.protocol !== "https:" || appUrl.protocol !== "https:" ||
      issuerUrl.username || issuerUrl.password || issuerUrl.search || issuerUrl.hash ||
      appUrl.username || appUrl.password || appUrl.search || appUrl.hash ||
      appUrl.pathname !== "/") {
    throw new Error("Hosted OIDC requires HTTPS issuer and application URLs.");
  }
  return { issuer, clientId, clientSecret, audience, parameter, secret, scopes };
}

export function authOptions(): NextAuthOptions {
  const config = configuration();
  return {
    secret: config.secret,
    session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
    providers: [{
      id: "oidc",
      name: "OpenID Connect",
      type: "oauth",
      issuer: config.issuer,
      wellKnown: `${config.issuer.replace(/\/$/, "")}/.well-known/openid-configuration`,
      clientId: config.clientId,
      clientSecret: config.clientSecret,
      authorization: { params: {
        scope: config.scopes,
        [config.parameter]: config.audience,
      } },
      checks: ["pkce", "state", "nonce"],
      idToken: true,
      profile(profile) {
        return { id: profile.sub, name: profile.name ?? null, email: profile.email ?? null, image: null };
      },
    }],
    callbacks: {
      async jwt({ token, account }) {
        if (account) {
          token.apiAccessToken = undefined;
          token.apiAccessTokenExpires = undefined;
          if (typeof account.access_token === "string" &&
              account.access_token !== account.id_token &&
              typeof account.expires_at === "number") {
            try {
              const claims = decodeJwt(account.access_token);
              const audiences = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
              if (claims.iss === config.issuer && audiences.includes(config.audience) &&
                  typeof claims.exp === "number") {
                token.apiAccessToken = account.access_token;
                token.apiAccessTokenExpires = Math.min(account.expires_at, claims.exp);
              }
            } catch {
              // Opaque or malformed access tokens cannot be accepted by the backend.
            }
          }
        }
        return token;
      },
      async session({ session, token }) {
        session.apiSessionValid = typeof token.apiAccessToken === "string" &&
          typeof token.apiAccessTokenExpires === "number" &&
          token.apiAccessTokenExpires > Math.floor(Date.now() / 1000);
        return session;
      },
    },
  };
}
