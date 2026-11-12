"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiClient, getApiErrorMessage } from "@/lib/api";

type HistoryEntry = {
  event_type?: string;
  status?: string;
  decision?: string;
  generation_id?: string;
  repository?: string;
  repository_path?: string;
  documentation_target?: string;
  documentation_file?: string;
  class_name?: string;
  method_name?: string;
  documentation?: string | null;
  timestamp?: string;
};

function isHistoryEntry(value: unknown): value is HistoryEntry {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const entry = value as Record<string, unknown>;
  return [
    "event_type", "status", "decision", "generation_id", "repository",
    "repository_path", "documentation_target", "documentation_file",
    "class_name", "method_name", "timestamp",
  ].every((key) => entry[key] === undefined || typeof entry[key] === "string")
    && (entry.documentation === undefined || entry.documentation === null || typeof entry.documentation === "string");
}

export default function HistoryPage() {
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiClient.get<{ history: unknown }>("/history");
      if (!Array.isArray(response.data.history) || !response.data.history.every(isHistoryEntry)) {
        throw new Error("The backend returned an invalid history response.");
      }
      setHistory(response.data.history);
    } catch (reason: unknown) {
      setHistory([]);
      setError(reason instanceof Error && reason.message === "The backend returned an invalid history response."
        ? reason.message : getApiErrorMessage(reason));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void fetchHistory(); }, 0);
    return () => window.clearTimeout(timer);
  }, [fetchHistory]);

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-7 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">History</h1>
          <p className="mt-2 text-sm text-slate-600">Decisions across all repositories.</p>
        </div>
        <button type="button" onClick={fetchHistory} disabled={loading} className="min-h-11 rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50">Refresh</button>
      </header>
      {error && <p role="alert" className="mb-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-900">{error}</p>}
      {loading ? (
        <p role="status" className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">Loading history…</p>
      ) : !error && history.length === 0 ? (
        <section className="rounded-xl border border-dashed border-slate-300 bg-white p-6">
          <h2 className="font-semibold">No decisions yet</h2>
          <Link href="/ai-documentation" className="mt-3 inline-block text-sm font-semibold text-cyan-800 hover:underline">Generate a preview</Link>
        </section>
      ) : (
        <section aria-label="Decision history" className="space-y-3">
          {[...history].reverse().map((item, index) => (
            <article key={`${item.generation_id ?? item.timestamp ?? "entry"}-${index}`} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap justify-between gap-3">
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold capitalize text-slate-700">{item.status ?? item.decision ?? "Unknown status"}</span>
                <time className="text-xs text-slate-500">{item.timestamp ? new Date(item.timestamp).toLocaleString() : "Time unavailable"}</time>
              </div>
              <p className="mt-4 break-all text-sm font-medium">{item.repository_path ?? item.repository ?? "Repository unavailable"}</p>
              <p className="mt-1 break-all text-sm text-slate-600">{item.documentation_target ?? item.documentation_file ?? "Target unavailable"}</p>
              {item.class_name && <p className="mt-1 text-sm text-slate-600">{item.class_name}{item.method_name ? `.${item.method_name}` : ""}</p>}
              {item.generation_id && (
                <p className="mt-3 break-all font-mono text-xs text-slate-500">Generation ID: {item.generation_id}</p>
              )}
              {item.documentation && <details className="mt-3 text-sm"><summary className="cursor-pointer font-medium">Saved documentation</summary><pre className="mt-2 whitespace-pre-wrap break-words">{item.documentation}</pre></details>}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
