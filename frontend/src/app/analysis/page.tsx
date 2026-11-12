"use client";

import { AlertCircle, LoaderCircle, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import AnalysisErrorPanel from "../components/repository/AnalysisErrorPanel";
import AnalysisModeSelector from "../components/repository/AnalysisModeSelector";
import AnalysisSummary from "../components/repository/AnalysisSummary";
import FileExplorer from "../components/repository/FileExplorer";
import GitChangeList from "../components/repository/GitChangeList";
import RepositoryPathInput from "../components/repository/RepositoryPathInput";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";
import {
  analyzeFullRepository,
  analyzeRepository,
  getApiErrorMessage,
} from "@/lib/api";
import type {
  AnalysisMode,
  AnalyzeResponse,
  FullAnalyzeResponse,
} from "@/types/api";

type AnalysisResult =
  | { mode: "full"; data: FullAnalyzeResponse }
  | { mode: "working_tree" | "commits"; data: AnalyzeResponse };

function isAbsoluteWindowsPath(path: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(path) || /^\\\\[^\\]+\\[^\\]+/.test(path);
}

export default function RepositoryAnalysisPage() {
  const { repositoryPath, setRepositoryPath } = useRepositoryAnalysis();
  const [mode, setMode] = useState<AnalysisMode>("full");
  const [baseCommit, setBaseCommit] = useState("");
  const [loading, setLoading] = useState(false);
  const [formError, setFormError] = useState("");
  const [requestError, setRequestError] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [analysisStatePath, setAnalysisStatePath] = useState(
    repositoryPath.trim()
  );
  const latestRequest = useRef(0);

  async function submitAnalysis(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const path = repositoryPath.trim();
    const requestId = ++latestRequest.current;
    setAnalysisStatePath(path);
    setFormError("");
    setRequestError("");
    setResult(null);
    setLoading(false);

    if (!path) {
      setFormError("Enter a repository path before starting analysis.");
      return;
    }
    if (!isAbsoluteWindowsPath(path)) {
      setFormError(
        "Enter an absolute Windows path, such as D:\\Projects\\MyJavaRepository."
      );
      return;
    }

    setLoading(true);

    try {
      if (mode === "full") {
        const data = await analyzeFullRepository(path);
        if (requestId === latestRequest.current) {
          setResult({ mode: "full", data });
        }
      } else {
        const request = {
          repository_path: path,
          mode,
          ...(mode === "commits" && baseCommit.trim()
            ? { base_commit: baseCommit.trim() }
            : {}),
        };
        const data = await analyzeRepository(request);
        if (requestId === latestRequest.current) {
          setResult({ mode, data });
        }
      }
    } catch (error: unknown) {
      if (requestId === latestRequest.current) {
        setRequestError(getApiErrorMessage(error));
      }
    } finally {
      if (requestId === latestRequest.current) {
        setLoading(false);
      }
    }
  }

  function clearResults() {
    latestRequest.current += 1;
    setAnalysisStatePath(repositoryPath.trim());
    setLoading(false);
    setFormError("");
    setRequestError("");
    setResult(null);
  }

  const isCurrentRepository = analysisStatePath === repositoryPath.trim();
  const currentLoading = isCurrentRepository && loading;
  const currentFormError = isCurrentRepository ? formError : "";
  const currentRequestError = isCurrentRepository ? requestError : "";
  const currentResult = isCurrentRepository ? result : null;
  const fullResult =
    currentResult?.mode === "full" ? currentResult.data : undefined;
  const gitResult =
    currentResult && currentResult.mode !== "full"
      ? currentResult.data
      : undefined;
  const hasPartialErrors = Boolean(
    fullResult?.errors.length ||
      gitResult?.results.some((file) => (file.errors?.length ?? 0) > 0)
  );

  return (
    <div className="mx-auto max-w-7xl">
      <header className="mb-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">
          Workspace
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
          Repository Analysis
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Scan the repository or inspect Git changes.
        </p>
      </header>

      <form
        onSubmit={submitAnalysis}
        noValidate
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"
      >
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(16rem,0.7fr)]">
          <RepositoryPathInput
            value={repositoryPath}
            onChange={(path) => {
              clearResults();
              setRepositoryPath(path);
            }}
            disabled={currentLoading}
          />
          <AnalysisModeSelector
            value={mode}
            onChange={setMode}
            disabled={currentLoading}
          />
        </div>

        {mode === "commits" && (
          <div className="mt-5 max-w-xl">
            <label
              htmlFor="base-commit"
              className="mb-2 block text-sm font-medium text-slate-800"
            >
              Base commit <span className="font-normal text-slate-500">(optional)</span>
            </label>
            <input
              id="base-commit"
              type="text"
              value={baseCommit}
              onChange={(event) => setBaseCommit(event.target.value)}
              placeholder="Commit hash or Git reference"
              autoComplete="off"
              disabled={currentLoading}
              className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10 disabled:cursor-not-allowed disabled:bg-slate-100"
            />
            <p className="mt-2 text-xs leading-5 text-slate-500">
              When omitted, the backend compares the current commit with its
              first parent.
            </p>
          </div>
        )}

        {currentFormError && (
          <div className="mt-5" aria-live="assertive">
            <AnalysisErrorPanel
              message={currentFormError}
              title="Check the repository path"
            />
          </div>
        )}
        {currentRequestError && (
          <div className="mt-5">
            <AnalysisErrorPanel
              message={currentRequestError}
              title="The backend could not complete this analysis"
            />
          </div>
        )}

        <div className="mt-6 flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={clearResults}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 aria-hidden="true" size={16} />
            Clear results
          </button>
          <button
            type="submit"
            disabled={currentLoading}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white outline-none hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70"
          >
            {currentLoading ? (
              <>
                <LoaderCircle aria-hidden="true" className="animate-spin" size={17} />
                Analyzing…
              </>
            ) : (
              <>
                <AlertCircle aria-hidden="true" size={16} />
                Analyze repository
              </>
            )}
          </button>
        </div>
      </form>

      {currentLoading && (
        <div
          role="status"
          aria-live="polite"
          className="mt-6 rounded-xl border border-cyan-100 bg-cyan-50 p-4 text-sm text-cyan-950"
        >
          Analysis is running on the local backend. Large repositories may take
          some time.
        </div>
      )}

      {currentResult && (
        <div className="mt-8 space-y-6">
          {hasPartialErrors && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Analysis completed with errors. Available results are shown below.
            </div>
          )}
          {fullResult && (
            <>
              <AnalysisSummary
                mode="full"
                repository={fullResult.repository}
                full={fullResult}
              />
              <AnalysisErrorPanel
                title="Some analysis steps reported errors"
                errors={fullResult.errors}
              />
              <FileExplorer
                files={fullResult.files}
                errors={fullResult.errors}
              />
            </>
          )}
          {gitResult && (
            <>
              <AnalysisSummary
                mode={gitResult.mode}
                repository={gitResult.repository}
                git={gitResult}
              />
              <GitChangeList results={gitResult.results} />
              <AnalysisErrorPanel
                title="Some changed files could not be fully analyzed"
                errors={gitResult.results.flatMap(
                  (file) => file.errors ?? []
                )}
              />
            </>
          )}
          <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cyan-100 bg-cyan-50 p-4">
            <p className="text-sm text-cyan-950">Next: review coverage or prepare documentation.</p>
            <div className="flex flex-wrap gap-3 text-sm font-semibold text-cyan-800">
              <Link href="/drift" className="hover:underline">View coverage & drift</Link>
              <Link href="/ai-documentation" className="hover:underline">Generate documentation</Link>
            </div>
          </section>
        </div>
      )}

      {!currentLoading &&
        !currentResult &&
        !currentRequestError &&
        !currentFormError && (
        <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-5 py-6 text-center">
          <p className="text-sm font-medium text-slate-700">
            No analysis results yet
          </p>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Enter a repository path and choose an analysis mode. No backend
            analysis runs when you open this page.
          </p>
        </div>
      )}
    </div>
  );
}
