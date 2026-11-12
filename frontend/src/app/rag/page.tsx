"use client";

import {
  AlertCircle,
  ArrowLeft,
  Database,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";
import { getApiErrorMessage, getRagStatus, indexRepository } from "@/lib/api";
import { getWindowsRepositoryIdentity } from "@/lib/repositoryIdentity";
import type { RagIndexResponse, RagStatusResponse } from "@/types/api";

interface RagIndexError {
  file: string | null;
  stage: string;
  message: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function parseIndexErrors(value: unknown): RagIndexError[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const parsed: RagIndexError[] = [];
  for (const item of value) {
    if (
      !isRecord(item) ||
      typeof item.stage !== "string" ||
      typeof item.message !== "string" ||
      (typeof item.file !== "string" && item.file !== null)
    ) {
      return null;
    }
    parsed.push({
      file: item.file,
      stage: item.stage,
      message: item.message,
    });
  }
  return parsed;
}

function isRagIndexResponse(value: unknown): value is RagIndexResponse {
  return (
    isRecord(value) &&
    typeof value.repository === "string" &&
    typeof value.repository_id === "string" &&
    isStringArray(value.indexed_files) &&
    isStringArray(value.skipped_files) &&
    isStringArray(value.deleted_files) &&
    typeof value.indexed_chunks === "number" &&
    Number.isInteger(value.indexed_chunks) &&
    value.indexed_chunks >= 0 &&
    parseIndexErrors(value.errors) !== null
  );
}

function isRagStatusResponse(value: unknown): value is RagStatusResponse {
  return (
    isRecord(value) &&
    typeof value.repository === "string" &&
    typeof value.repository_id === "string" &&
    typeof value.index_available === "boolean" &&
    (typeof value.indexed_document_count === "number" ||
      value.indexed_document_count === null) &&
    (typeof value.chunk_count === "number" || value.chunk_count === null) &&
    (typeof value.last_successful_indexing === "string" ||
      value.last_successful_indexing === null)
  );
}

function absoluteWindowsPath(path: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(path) || /^\\\\[^\\]+\\[^\\]+/.test(path);
}

function safeErrorMessage(error: unknown): string {
  const message = getApiErrorMessage(error);
  return /Traceback \(most recent call last\):/.test(message) ||
    /File ".*", line \d+/.test(message)
    ? "The backend reported an internal error. See the FastAPI logs for details."
    : message;
}

function ErrorPanel({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-900"
    >
      <AlertCircle aria-hidden="true" size={18} className="mt-1 shrink-0" />
      <p className="break-words">{message}</p>
    </div>
  );
}

export default function RagIndexPage() {
  const { repositoryPath } = useRepositoryAnalysis();
  return (
    <RagIndexContent key={repositoryPath} repositoryPath={repositoryPath} />
  );
}

function RagIndexContent({ repositoryPath }: { repositoryPath: string }) {
  const selectedPath = repositoryPath.trim();
  const [indexResult, setIndexResult] = useState<RagIndexResponse | null>(null);
  const [ragStatus, setRagStatus] = useState<RagStatusResponse | null>(null);
  const [indexError, setIndexError] = useState("");
  const [statusError, setStatusError] = useState("");
  const [isIndexing, setIsIndexing] = useState(false);
  const [isLoadingStatus, setIsLoadingStatus] = useState(false);
  const indexRequest = useRef(0);
  const statusRequest = useRef(0);
  const indexController = useRef<AbortController | null>(null);
  const statusController = useRef<AbortController | null>(null);

  useEffect(
    () => () => {
      indexRequest.current += 1;
      statusRequest.current += 1;
      indexController.current?.abort();
      statusController.current?.abort();
    },
    []
  );

  async function selectedRepositoryIdentity(): Promise<string> {
    if (!selectedPath) {
      throw new Error("Select a repository in Repository Analysis first.");
    }
    if (!absoluteWindowsPath(selectedPath)) {
      throw new Error(
        "The selected repository path must be an absolute Windows path."
      );
    }
    const identity = await getWindowsRepositoryIdentity(selectedPath);
    if (!identity) {
      throw new Error(
        "Repository identity could not be calculated in this browser. No index request was sent."
      );
    }
    return identity;
  }

  async function runIndexing() {
    if (isIndexing || isLoadingStatus) {
      return;
    }
    const requestId = ++indexRequest.current;
    indexController.current?.abort();
    const controller = new AbortController();
    indexController.current = controller;
    setIndexError("");
    setIndexResult(null);
    setRagStatus(null);
    setStatusError("");

    let expectedIdentity: string;
    try {
      expectedIdentity = await selectedRepositoryIdentity();
    } catch (error: unknown) {
      setIndexError(error instanceof Error ? error.message : safeErrorMessage(error));
      return;
    }

    setIsIndexing(true);
    try {
      const response = await indexRepository(
        { repository_path: selectedPath },
        controller.signal
      );
      if (requestId !== indexRequest.current) {
        return;
      }
      if (!isRagIndexResponse(response)) {
        setIndexError(
          "The backend returned an incomplete or unexpected indexing response."
        );
        return;
      }
      if (response.repository_id !== expectedIdentity) {
        setIndexError(
          "The backend repository identity did not match the selected repository. Index results were withheld."
        );
        return;
      }
      setIndexResult(response);
    } catch (error: unknown) {
      if (requestId === indexRequest.current && !controller.signal.aborted) {
        setIndexError(safeErrorMessage(error));
      }
    } finally {
      if (requestId === indexRequest.current) {
        setIsIndexing(false);
        indexController.current = null;
      }
    }
  }

  async function loadStatus() {
    if (isLoadingStatus || isIndexing) {
      return;
    }
    const requestId = ++statusRequest.current;
    statusController.current?.abort();
    const controller = new AbortController();
    statusController.current = controller;
    setStatusError("");
    setRagStatus(null);

    let expectedIdentity: string;
    try {
      expectedIdentity = await selectedRepositoryIdentity();
    } catch (error: unknown) {
      setStatusError(error instanceof Error ? error.message : safeErrorMessage(error));
      return;
    }

    setIsLoadingStatus(true);
    try {
      const response = await getRagStatus(selectedPath, controller.signal);
      if (requestId !== statusRequest.current) {
        return;
      }
      if (!isRagStatusResponse(response)) {
        setStatusError(
          "The backend returned an incomplete or unexpected RAG status response."
        );
        return;
      }
      if (response.repository_id !== expectedIdentity) {
        setStatusError(
          "The backend repository identity did not match the selected repository. Status details were withheld."
        );
        return;
      }
      setRagStatus(response);
    } catch (error: unknown) {
      if (requestId === statusRequest.current && !controller.signal.aborted) {
        setStatusError(safeErrorMessage(error));
      }
    } finally {
      if (requestId === statusRequest.current) {
        setIsLoadingStatus(false);
        statusController.current = null;
      }
    }
  }

  if (!selectedPath) {
    return (
      <div className="mx-auto max-w-4xl">
        <header className="mb-7">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">
            Repository-scoped context
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
            RAG Index
          </h1>
        </header>
        <section className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center shadow-sm">
          <Database
            aria-hidden="true"
            className="mx-auto text-slate-400"
            size={28}
          />
          <h2 className="mt-4 text-lg font-semibold text-slate-950">
            Select a repository to manage its documentation index
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600">
            Indexing and status checks are never started automatically when this
            page opens.
          </p>
          <Link
            href="/analysis"
            className="mt-5 inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white outline-none hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2"
          >
            <ArrowLeft aria-hidden="true" size={16} />
            Repository Analysis
          </Link>
        </section>
      </div>
    );
  }

  const indexErrors = indexResult
    ? parseIndexErrors(indexResult.errors) ?? []
    : [];
  const hasIndexErrors = indexErrors.length > 0;

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">
            Repository-scoped context
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
            RAG Index
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            Inspect or explicitly index the selected repository’s Markdown
            documentation. This page does not expose ChromaDB collections or
            delete indexed data.
          </p>
        </div>
        <Link
          href="/analysis"
          className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2"
        >
          <ArrowLeft aria-hidden="true" size={16} />
          Repository Analysis
        </Link>
      </header>

      <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
          Selected repository
        </p>
        <p className="mt-2 break-all font-mono text-sm leading-6 text-slate-900">
          {selectedPath}
        </p>
        <div className="mt-5 flex flex-col gap-3 border-t border-slate-100 pt-5 sm:flex-row">
          <button
            type="button"
            onClick={() => void runIndexing()}
            disabled={isIndexing || isLoadingStatus}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-cyan-800 px-4 text-sm font-semibold text-white outline-none hover:bg-cyan-900 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70"
          >
            {isIndexing ? (
              <LoaderCircle
                aria-hidden="true"
                size={17}
                className="animate-spin"
              />
            ) : (
              <Database aria-hidden="true" size={17} />
            )}
            {isIndexing ? "Indexing documentation…" : "Index Documentation"}
          </button>
          <button
            type="button"
            onClick={() => void loadStatus()}
            disabled={isLoadingStatus || isIndexing}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70"
          >
            {isLoadingStatus ? (
              <LoaderCircle
                aria-hidden="true"
                size={17}
                className="animate-spin"
              />
            ) : (
              <RefreshCw aria-hidden="true" size={16} />
            )}
            {isLoadingStatus ? "Checking index status…" : "Check Index Status"}
          </button>
        </div>
        {isIndexing && (
          <p role="status" className="mt-4 text-sm leading-6 text-cyan-800">
            The backend is scanning repository Markdown and updating its
            repository-scoped vector index. Larger repositories may take time.
          </p>
        )}
        {isLoadingStatus && (
          <p role="status" className="mt-4 text-sm leading-6 text-cyan-800">
            Requesting a read-only status from the backend.
          </p>
        )}
        {indexError && (
          <div className="mt-4">
            <ErrorPanel message={indexError} />
          </div>
        )}
        {statusError && (
          <div className="mt-4">
            <ErrorPanel message={statusError} />
          </div>
        )}
      </section>

      {indexResult && (
        <section
          aria-labelledby="rag-index-result-heading"
          className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
        >
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2
                id="rag-index-result-heading"
                className="text-lg font-semibold text-slate-950"
              >
                Indexing result
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Backend-derived repository identity verified against the
                selected path.
              </p>
            </div>
            <span
              className={`inline-flex w-fit rounded-full border px-3 py-1 text-xs font-semibold ${
                hasIndexErrors
                  ? "border-amber-200 bg-amber-50 text-amber-900"
                  : "border-emerald-200 bg-emerald-50 text-emerald-900"
              }`}
            >
              {hasIndexErrors ? "Completed with errors" : "Completed"}
            </span>
          </div>
          <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Indexed documents", indexResult.indexed_files.length],
              ["Skipped files", indexResult.skipped_files.length],
              ["Removed documents", indexResult.deleted_files.length],
              ["Indexed chunks", indexResult.indexed_chunks],
            ].map(([label, count]) => (
              <div
                key={label}
                className="rounded-xl border border-slate-100 bg-slate-50 p-4"
              >
                <dt className="text-xs font-medium text-slate-500">{label}</dt>
                <dd className="mt-1 text-xl font-semibold text-slate-950">
                  {count}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-4 rounded-lg border border-slate-100 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Backend repository identity
            </p>
            <p className="mt-1 break-all font-mono text-xs leading-5 text-slate-700">
              {indexResult.repository_id}
            </p>
          </div>
          {indexResult.indexed_files.length === 0 &&
            indexResult.skipped_files.length === 0 &&
            !hasIndexErrors && (
              <p className="mt-4 text-sm leading-6 text-slate-600">
                The backend reported no indexable Markdown documents for this
                repository.
              </p>
            )}
          {hasIndexErrors && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
              <h3 className="text-sm font-semibold text-amber-950">
                Backend-reported indexing errors
              </h3>
              <ul className="mt-2 space-y-3 text-sm leading-6 text-amber-950">
                {indexErrors.map((error, index) => (
                  <li
                    key={`${error.stage}-${error.file ?? "repository"}-${index}`}
                  >
                    <p className="font-medium">
                      {error.stage}
                      {error.file ? ` · ${error.file}` : ""}
                    </p>
                    <p className="break-words">{error.message}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {ragStatus && (
        <section
          aria-labelledby="rag-status-heading"
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
        >
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-cyan-50 text-cyan-800">
              <ShieldCheck aria-hidden="true" size={20} />
            </span>
            <div>
              <h2
                id="rag-status-heading"
                className="text-lg font-semibold text-slate-950"
              >
                Repository index status
              </h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                Read-only status returned for the selected repository. No
                indexing is performed by this status request.
              </p>
            </div>
          </div>
          {!ragStatus.index_available ? (
            <p
              role="status"
              className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950"
            >
              The backend reports that the vector index is unavailable.
              Indexed document and chunk counts were not provided.
            </p>
          ) : (
            <dl className="mt-5 grid gap-3 sm:grid-cols-2">
              {[
                [
                  "Indexed documentation files",
                  ragStatus.indexed_document_count,
                ],
                ["Indexed chunks", ragStatus.chunk_count],
                [
                  "Last successful indexing",
                  ragStatus.last_successful_indexing ?? "Not provided by backend",
                ],
              ].map(([label, value]) => (
                <div
                  key={label}
                  className="rounded-xl border border-slate-100 bg-slate-50 p-4"
                >
                  <dt className="text-xs font-medium text-slate-500">{label}</dt>
                  <dd className="mt-1 break-words text-sm font-semibold text-slate-900">
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <div className="mt-4 rounded-lg border border-slate-100 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Backend repository identity
            </p>
            <p className="mt-1 break-all font-mono text-xs leading-5 text-slate-700">
              {ragStatus.repository_id}
            </p>
          </div>
          {ragStatus.index_available &&
            ragStatus.indexed_document_count === 0 && (
              <p className="mt-4 text-sm text-slate-600">
                The index is available but currently contains no documentation
                files. Use Index Documentation to explicitly scan the
                repository.
              </p>
            )}
        </section>
      )}
    </div>
  );
}
