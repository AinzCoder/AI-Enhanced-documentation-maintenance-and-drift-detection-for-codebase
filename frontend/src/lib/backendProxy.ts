import { getToken } from "next-auth/jwt";
import { NextRequest } from "next/server";
import { isHosted } from "@/lib/deployment";

const routes: Record<string, string[]> = {
  GET: ["/", "/repositories", "/history", "/rag/status"],
  POST: ["/analyze", "/analyze/full", "/rag/index", "/suggest", "/decision", "/documentation/generate/full"],
};

function permitted(method: string, path: string): boolean {
  if (routes[method]?.includes(path)) return true;
  return /^\/documentation\/generation\/[A-Za-z0-9_-]+$/.test(path) && method === "GET" ||
    /^\/documentation\/generation\/[A-Za-z0-9_-]+\/(approve|reject)$/.test(path) && method === "POST";
}

function backendUrl(): URL | null {
  try {
    const url = new URL(process.env.DOCGUARD_BACKEND_URL || "");
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash ||
        url.pathname !== "/") return null;
    return url;
  } catch {
    return null;
  }
}

function sameOrigin(request: NextRequest): boolean {
  try {
    return request.headers.get("origin") === new URL(process.env.NEXTAUTH_URL || "").origin;
  } catch {
    return false;
  }
}

function translateRepository(value: Record<string, unknown>): boolean {
  if (!("repository_path" in value)) return true;
  if (typeof value.repository_path !== "string" ||
      !/^[0-9a-f]{32}$/.test(value.repository_path) || "repository_id" in value) return false;
  value.repository_id = value.repository_path;
  delete value.repository_path;
  return true;
}

export async function backendProxy(request: NextRequest, path: string) {
  if (!isHosted) return new Response("Not found", { status: 404 });
  if (!permitted(request.method, path)) return new Response("Not found", { status: 404 });
  if (request.method !== "GET" && !sameOrigin(request)) return new Response("Forbidden", { status: 403 });
  const base = backendUrl();
  if (!base || !process.env.NEXTAUTH_SECRET || !process.env.NEXTAUTH_URL)
    return new Response("Hosted configuration is incomplete.", { status: 503 });
  const cookieRequest = new NextRequest(request.url, { headers: { cookie: request.headers.get("cookie") || "" } });
  const session = await getToken({ req: cookieRequest, secret: process.env.NEXTAUTH_SECRET });
  if (!session || typeof session.apiAccessToken !== "string" ||
      typeof session.apiAccessTokenExpires !== "number" ||
      session.apiAccessTokenExpires <= Math.floor(Date.now() / 1000)) {
    return Response.json({ detail: "Your session has expired. Sign in again." }, { status: 401 });
  }
  const url = new URL(path, base);
  const params = new URL(request.url).searchParams;
  if (params.has("repository_path")) {
    const pathValue = params.get("repository_path");
    if (!pathValue || !/^[0-9a-f]{32}$/.test(pathValue) || params.has("repository_id"))
      return Response.json({ detail: "Select a hosted repository." }, { status: 400 });
    params.delete("repository_path");
    params.set("repository_id", pathValue);
  }
  url.search = params.toString();
  let body: string | undefined;
  if (request.method !== "GET") {
    const size = Number(request.headers.get("content-length") || "0");
    if (!Number.isFinite(size) || size > 1_000_000) return new Response("Request too large", { status: 413 });
    const reader = request.body?.getReader();
    const decoder = new TextDecoder();
    let text = "";
    let bytes = 0;
    if (reader) {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        bytes += value.byteLength;
        if (bytes > 1_000_000) {
          await reader.cancel();
          return new Response("Request too large", { status: 413 });
        }
        text += decoder.decode(value, { stream: true });
      }
      text += decoder.decode();
    }
    try {
      const parsed: unknown = JSON.parse(text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) ||
          !translateRepository(parsed as Record<string, unknown>))
        return Response.json({ detail: "Select a hosted repository." }, { status: 400 });
      body = JSON.stringify(parsed);
    } catch {
      return new Response("Invalid request", { status: 400 });
    }
  }
  try {
    const response = await fetch(url, {
      method: request.method,
      headers: { authorization: `Bearer ${session.apiAccessToken}`, ...(body ? { "content-type": "application/json" } : {}) },
      body,
      redirect: "error",
      cache: "no-store",
      signal: request.signal,
    });
    const headers = new Headers({ "Cache-Control": "no-store" });
    const contentType = response.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    return new Response(response.body, { status: response.status, headers });
  } catch {
    return Response.json({ detail: "Could not reach the backend." }, { status: 502 });
  }
}
