"use client";

import { signIn, signOut } from "next-auth/react";

export default function AuthControls({ name, expired = false }: { name?: string | null; expired?: boolean }) {
  if (!name || expired) {
    return <div className="rounded-xl border border-slate-200 bg-white p-6">
      <h1 className="text-xl font-semibold">Sign in to DocGuard</h1>
      <p className="mt-2 text-sm text-slate-600">
        {expired ? "Your session has expired or the provider did not issue an API access token. Sign in again." : "Sign in to access your hosted workspace."}
      </p>
      <button className="mt-4 rounded-lg bg-cyan-700 px-4 py-2 text-white" onClick={() => void signIn("oidc", { callbackUrl: "/" })}>Sign in</button>
      {expired && <button className="ml-3 text-sm text-slate-700" onClick={() => void signOut({ callbackUrl: "/" })}>Sign out</button>}
    </div>;
  }
  return <div className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-6 py-3 text-sm">
    <span>Signed in as {name}</span>
    <button className="font-semibold text-cyan-800" onClick={() => void signOut({ callbackUrl: "/" })}>Sign out</button>
  </div>;
}
