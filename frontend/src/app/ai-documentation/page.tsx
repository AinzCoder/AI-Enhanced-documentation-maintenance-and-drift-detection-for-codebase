"use client";

import {
  AlertCircle,
  ArrowLeft,
  FileText,
  LoaderCircle,
  Search,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import GeneratedDocumentationPreview from "../components/documentation/GeneratedDocumentationPreview";
import GenerationReviewPanel from "../components/documentation/GenerationReviewPanel";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";
import {
  generateFullDocumentation,
  getApiErrorMessage,
  getGeneration,
} from "@/lib/api";
import { getWindowsRepositoryIdentity } from "@/lib/repositoryIdentity";
import { isValidRepositorySelection } from "@/lib/repositorySelection";
import type {
  AnalysisError,
  DocumentationIndexingSummary,
  FullDocumentationRequest,
  GenerationRecord,
  GenerationStatus,
  RetrievalSummary,
} from "@/types/api";

interface GenerationSnapshot {
  source: "generated" | "retrieved";
  repositoryPath: string;
  repository: string;
  documentationTarget: string | null;
  generatedMarkdown: string | null;
  generationStatus: GenerationStatus | null;
  generationId: string | null;
  approvalStatus: string | null;
  sourceHashes: Record<string, string>;
  targetHash: string | null;
  generatedClassCount: number | null;
  generatedMethodCount: number | null;
  skippedMethodCount: number | null;
  maxMethodsRequested: number | null;
  errors: AnalysisError[];
  retrieval: RetrievalSummary | null;
  contextLimits: Record<string, number>;
  createdAt: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseErrors(value: unknown): AnalysisError[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (!isRecord(item) || typeof item.stage !== "string" || typeof item.message !== "string") {
      return [];
    }
    return [{
      stage: item.stage,
      file: typeof item.file === "string" ? item.file : null,
      message: item.message,
    }];
  });
}

function parseStringRecord(value: unknown): Record<string, string> {
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string"
    )
  );
}

function parseNumberRecord(value: unknown): Record<string, number> {
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, number] =>
        typeof entry[1] === "number" && Number.isFinite(entry[1])
    )
  );
}

function parseIndexing(value: unknown): DocumentationIndexingSummary | null {
  if (!isRecord(value)) {
    return null;
  }
  const keys = [
    "indexed_files",
    "skipped_files",
    "deleted_files",
    "indexed_chunks",
    "error_count",
  ] as const;
  const values = keys.map((key) => numberValue(value[key]));
  if (values.some((count) => count === null)) {
    return null;
  }
  return {
    indexed_files: values[0]!,
    skipped_files: values[1]!,
    deleted_files: values[2]!,
    indexed_chunks: values[3]!,
    error_count: values[4]!,
  };
}

function parseRetrieval(value: unknown): RetrievalSummary | null {
  if (!isRecord(value)) {
    return null;
  }
  const indexing = value.indexing;
  return {
    strategy: stringValue(value.strategy) ?? undefined,
    vector_store_used:
      typeof value.vector_store_used === "boolean"
        ? value.vector_store_used
        : undefined,
    repository_scoped:
      typeof value.repository_scoped === "boolean"
        ? value.repository_scoped
        : undefined,
    fallback_used:
      typeof value.fallback_used === "boolean"
        ? value.fallback_used
        : undefined,
    fallback_count: numberValue(value.fallback_count) ?? undefined,
    query_count: numberValue(value.query_count) ?? undefined,
    retrieved_chunks: numberValue(value.retrieved_chunks) ?? undefined,
    indexing: indexing === null ? null : parseIndexing(indexing),
    errors: parseErrors(value.errors),
  };
}

function countIfArray(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null;
}

function hasGenerationResponseShape(value: unknown): value is Record<string, unknown> {
  return (
    isRecord(value) &&
    typeof value.repository === "string" &&
    typeof value.documentation_target === "string" &&
    (value.generated_markdown === null ||
      typeof value.generated_markdown === "string") &&
    ["complete", "partial", "failed"].includes(
      String(value.generation_status)
    ) &&
    Array.isArray(value.generated_classes) &&
    Array.isArray(value.generated_methods) &&
    Array.isArray(value.skipped_documented_methods) &&
    Array.isArray(value.errors) &&
    isRecord(value.source_hashes) &&
    typeof value.target_hash_at_generation === "string"
  );
}

function hasGenerationRecordShape(value: unknown): value is GenerationRecord {
  return (
    isRecord(value) &&
    typeof value.generation_id === "string" &&
    typeof value.repository === "string" &&
    typeof value.repository_identity === "string" &&
    typeof value.documentation_target === "string" &&
    typeof value.generated_markdown === "string" &&
    ["complete", "partial", "failed"].includes(
      String(value.generation_status)
    ) &&
    typeof value.status === "string" &&
    isRecord(value.source_hashes)
  );
}

function parseGenerationSnapshot(
  value: unknown,
  repositoryPath: string,
  source: GenerationSnapshot["source"],
  maxMethodsRequested: number | null = null
): GenerationSnapshot | null {
  if (!isRecord(value)) {
    return null;
  }
  const rawStatus = stringValue(value.generation_status);
  const generationStatus =
    rawStatus === "complete" || rawStatus === "partial" || rawStatus === "failed"
      ? rawStatus
      : null;
  const rawMarkdown = value.generated_markdown;

  return {
    source,
    repositoryPath,
    repository: stringValue(value.repository) ?? "Not available",
    documentationTarget: stringValue(value.documentation_target),
    generatedMarkdown:
      typeof rawMarkdown === "string" ? rawMarkdown : null,
    generationStatus,
    generationId: stringValue(value.generation_id),
    approvalStatus: stringValue(
      source === "generated" ? value.approval_status : value.status
    ),
    sourceHashes: parseStringRecord(value.source_hashes),
    targetHash:
      stringValue(
        source === "generated"
          ? value.target_hash_at_generation
          : value.target_hash_before
      ),
    generatedClassCount: countIfArray(value.generated_classes),
    generatedMethodCount: countIfArray(value.generated_methods),
    skippedMethodCount: countIfArray(value.skipped_documented_methods),
    maxMethodsRequested,
    errors: parseErrors(value.errors),
    retrieval: parseRetrieval(value.retrieval),
    contextLimits: parseNumberRecord(value.context_limits),
    createdAt: stringValue(value.created_at),
  };
}

function safeErrorMessage(error: unknown): string {
  const message = getApiErrorMessage(error);
  return /Traceback \(most recent call last\):/.test(message) ||
    /File ".*", line \d+/.test(message)
    ? "The backend reported an internal error. See the FastAPI logs for details."
    : message;
}

function isAbsoluteWindowsPath(path: string): boolean {
  return isValidRepositorySelection(path);
}

function validateTarget(path: string): string | null {
  if (!path.trim()) {
    return "Enter a repository-relative Markdown target. The backend’s implicit default is not selected automatically.";
  }
  const target = path.trim();
  if (
    target.startsWith("/") ||
    target.startsWith("\\") ||
    /^[A-Za-z]:/.test(target)
  ) {
    return "The documentation target must be relative to the selected repository.";
  }
  if (target.split(/[\\/]+/).includes("..")) {
    return "The documentation target cannot contain a '..' path segment.";
  }
  if (!target.toLowerCase().endsWith(".md")) {
    return "The documentation target must use the .md extension.";
  }
  return null;
}

function StatusPill({ children }: { children: string }) {
  return (
    <span className="inline-flex rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700">
      {children}
    </span>
  );
}

function ErrorPanel({
  title,
  message,
}: {
  title: string;
  message: string;
}) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-900"
    >
      <AlertCircle aria-hidden="true" size={18} className="mt-1 shrink-0" />
      <div>
        <p className="font-semibold">{title}</p>
        <p className="mt-1 break-words">{message}</p>
      </div>
    </div>
  );
}

export default function AiDocumentationPage() {
  const { repositoryPath } = useRepositoryAnalysis();
  return (
    <AiDocumentationContent
      key={repositoryPath}
      repositoryPath={repositoryPath}
    />
  );
}

function AiDocumentationContent({
  repositoryPath,
}: {
  repositoryPath: string;
}) {
  const selectedPath = repositoryPath.trim();
  const [targetPath, setTargetPath] = useState("");
  const [includeOverview, setIncludeOverview] = useState(true);
  const [maxMethods, setMaxMethods] = useState("");
  const [generationError, setGenerationError] = useState("");
  const [formError, setFormError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [snapshot, setSnapshot] = useState<GenerationSnapshot | null>(null);
  const [verifiedRecord, setVerifiedRecord] =
    useState<GenerationRecord | null>(null);
  const [generationNotice, setGenerationNotice] = useState("");
  const [generationIdInput, setGenerationIdInput] = useState("");
  const [lookupError, setLookupError] = useState("");
  const [lookupNotice, setLookupNotice] = useState("");
  const [isLookingUp, setIsLookingUp] = useState(false);
  const generationRequest = useRef(0);
  const lookupRequest = useRef(0);
  const generationController = useRef<AbortController | null>(null);
  const lookupController = useRef<AbortController | null>(null);

  useEffect(() => {
    const requestId = ++lookupRequest.current;
    const controller = new AbortController();
    let active = true;
    async function restoreLastPreview() {
      if (!isAbsoluteWindowsPath(selectedPath)) {
        return;
      }
      const identity = await getWindowsRepositoryIdentity(selectedPath);
      if (!active || !identity) {
        return;
      }
      let generationId: string | null = null;
      try {
        generationId = sessionStorage.getItem(
          `docguard:last-generation:${identity}`
        );
      } catch {
        return;
      }
      if (!generationId) {
        return;
      }
      setGenerationIdInput(generationId);
      setIsLookingUp(true);
      try {
        const record = await getGeneration(generationId, controller.signal);
        if (
          !active ||
          requestId !== lookupRequest.current ||
          !hasGenerationRecordShape(record)
        ) {
          return;
        }
        if (record.repository_identity !== identity) {
          setLookupError(
            "The saved preview belongs to a different repository identity and was withheld."
          );
          return;
        }
        setVerifiedRecord(record);
        setSnapshot(parseGenerationSnapshot(record, selectedPath, "retrieved"));
        setLookupNotice(
          `Restored the saved preview after checking backend status “${record.status}”.`
        );
      } catch (error: unknown) {
        if (active && !controller.signal.aborted) {
          setLookupError(
            `Could not refresh the saved preview status: ${safeErrorMessage(error)}`
          );
        }
      } finally {
        if (active && requestId === lookupRequest.current) {
          setIsLookingUp(false);
        }
      }
    }
    void restoreLastPreview();
    return () => {
      active = false;
      controller.abort();
      generationRequest.current += 1;
      lookupRequest.current += 1;
      generationController.current?.abort();
      lookupController.current?.abort();
    };
  }, [selectedPath]);

  async function rememberVerifiedRecord(
    record: GenerationRecord,
    path: string
  ): Promise<boolean> {
    if (!hasGenerationRecordShape(record)) {
      return false;
    }
    const identity = await getWindowsRepositoryIdentity(path);
    if (!identity || identity !== record.repository_identity) {
      return false;
    }
    setVerifiedRecord(record);
    try {
      sessionStorage.setItem(
        `docguard:last-generation:${identity}`,
        record.generation_id
      );
    } catch {
      setLookupNotice(
        "Preview ownership is verified for this page, but this browser could not save its ID for restoration after navigation."
      );
    }
    setSnapshot((current) =>
      current
        ? {
            ...current,
            generatedMarkdown: record.generated_markdown,
            approvalStatus: record.status,
            documentationTarget: record.documentation_target,
            targetHash: record.target_hash_before,
            sourceHashes: parseStringRecord(record.source_hashes),
            generationStatus: record.generation_status,
          }
        : current
    );
    return true;
  }

  async function submitGeneration(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isGenerating || isLookingUp || generationController.current) {
      return;
    }
    setFormError("");
    setGenerationError("");
    setGenerationNotice("");
    setLookupError("");
    setLookupNotice("");
    setSnapshot(null);
    setVerifiedRecord(null);

    if (!selectedPath) {
      setFormError("Select a repository in Repository Analysis first.");
      return;
    }
    if (!isAbsoluteWindowsPath(selectedPath)) {
      setFormError(
        "Enter an absolute Windows repository path in Repository Analysis."
      );
      return;
    }
    const targetError = validateTarget(targetPath);
    if (targetError) {
      setFormError(targetError);
      return;
    }

    const parsedMaxMethods =
      maxMethods.trim() === "" ? undefined : Number(maxMethods);
    if (
      parsedMaxMethods !== undefined &&
      (!Number.isInteger(parsedMaxMethods) || parsedMaxMethods <= 0)
    ) {
      setFormError("Maximum methods must be a positive whole number.");
      return;
    }

    const request: FullDocumentationRequest = {
      repository_path: selectedPath,
      target_documentation_file: targetPath.trim(),
      include_repository_overview: includeOverview,
      ...(parsedMaxMethods === undefined
        ? {}
        : { max_methods: parsedMaxMethods }),
    };

    const requestId = ++generationRequest.current;
    const controller = new AbortController();
    generationController.current = controller;
    setIsGenerating(true);
    try {
      const response = await generateFullDocumentation(
        request,
        controller.signal
      );
      if (requestId !== generationRequest.current) {
        return;
      }
      if (!hasGenerationResponseShape(response)) {
        setGenerationError(
          "The backend returned an incomplete or unexpected generation response. No preview was shown."
        );
        return;
      }
      const parsed = parseGenerationSnapshot(
        response,
        selectedPath,
        "generated",
        parsedMaxMethods ?? null
      );
      if (!parsed || !parsed.generationStatus) {
        setGenerationError(
          "The backend returned an incomplete or unexpected generation response. No preview was shown."
        );
        return;
      }
      setSnapshot(parsed);
      setVerifiedRecord(null);
      const providerError = !parsed.generationId
        ? parsed.errors.find((error) =>
            ["class_generation", "method_generation", "overview_generation"].includes(error.stage ?? "")
          )
        : undefined;
      if (providerError?.message) {
        setGenerationNotice(providerError.message);
      } else if (
        parsed.generationStatus === "failed" ||
        !parsed.generatedMarkdown?.trim()
      ) {
        setGenerationNotice(
          "The backend did not return usable generated Markdown. Review the status and errors below; no successful preview is available."
        );
      } else if (parsed.generationStatus === "partial") {
        setGenerationNotice(
          "Generation completed partially. Review all backend errors and warnings before using this preview."
        );
      } else {
        setGenerationNotice("Generation completed. Review the preview and metadata below.");
      }
      if (parsed.generationId) {
        try {
          const identity = await getWindowsRepositoryIdentity(selectedPath);
          if (identity) {
            try {
              sessionStorage.setItem(
                `docguard:last-generation:${identity}`,
                parsed.generationId
              );
            } catch {
              setLookupNotice(
                "The preview was created, but this browser cannot save its ID for restoration after navigation."
              );
            }
          }
          const record = await getGeneration(parsed.generationId);
          if (requestId !== generationRequest.current) {
            return;
          }
          const verified = await rememberVerifiedRecord(record, selectedPath);
          if (!verified) {
            setLookupNotice(
              "The generation response was displayed, but the persisted record’s repository identity could not be verified. Approval and rejection are unavailable."
            );
          }
        } catch (error: unknown) {
          if (requestId === generationRequest.current) {
            setLookupNotice(
              `The generated preview is available, but its persisted status could not be verified. No review actions are available: ${safeErrorMessage(error)}`
            );
          }
        }
      }
    } catch (error: unknown) {
      if (
        requestId === generationRequest.current &&
        !controller.signal.aborted
      ) {
        setGenerationError(safeErrorMessage(error));
      }
    } finally {
      if (requestId === generationRequest.current) {
        setIsGenerating(false);
        generationController.current = null;
      }
    }
  }

  async function lookupGeneration(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isLookingUp || isGenerating) {
      return;
    }
    const generationId = generationIdInput.trim();
    const requestId = ++lookupRequest.current;
    lookupController.current?.abort();
    const controller = new AbortController();
    lookupController.current = controller;
    setLookupError("");
    setLookupNotice("");
    setGenerationError("");
    setSnapshot(null);
    setVerifiedRecord(null);
    setGenerationNotice("");

    if (!generationId) {
      setLookupError("Enter a generation ID.");
      return;
    }
    if (!selectedPath) {
      setLookupError("Select a repository before retrieving a preview.");
      return;
    }
    if (!isAbsoluteWindowsPath(selectedPath)) {
      setLookupError(
        "The selected repository path must be an absolute Windows path before ownership can be checked."
      );
      return;
    }

    setIsLookingUp(true);
    try {
      const record = await getGeneration(generationId, controller.signal);
      if (requestId !== lookupRequest.current) {
        return;
      }
      if (!hasGenerationRecordShape(record)) {
        setLookupError("The persisted generation record is incomplete or malformed.");
        return;
      }
      const recordIdentity = stringValue(record.repository_identity);
      if (!recordIdentity) {
        setLookupNotice(
          "This backend record does not contain a repository identity. Ownership cannot be verified, so its content is withheld."
        );
        return;
      }
      let selectedIdentity: string | null;
      try {
        selectedIdentity = await getWindowsRepositoryIdentity(selectedPath);
      } catch {
        selectedIdentity = null;
      }
      if (requestId !== lookupRequest.current) {
        return;
      }
      if (!selectedIdentity) {
        setLookupNotice(
          "This browser cannot safely calculate the selected repository identity. Ownership cannot be verified, so the preview is withheld."
        );
        return;
      }
      if (selectedIdentity !== recordIdentity) {
        setLookupError(
          "The generation belongs to a different repository identity. Its content was not displayed."
        );
        return;
      }
      const parsed = parseGenerationSnapshot(
        record,
        selectedPath,
        "retrieved"
      );
      if (!parsed) {
        setLookupError(
          "The persisted generation record is incomplete or malformed."
        );
        return;
      }
      setSnapshot(parsed);
      setVerifiedRecord(record);
      try {
        sessionStorage.setItem(
          `docguard:last-generation:${selectedIdentity}`,
          record.generation_id
        );
      } catch {
        setLookupNotice(
          "Repository ownership verified, but this browser could not save the preview ID for restoration after navigation."
        );
      }
      if (!parsed.generatedMarkdown?.trim()) {
        setLookupNotice(
          "Repository ownership was verified, but this record has no usable generated Markdown content."
        );
      } else if (!parsed.generationStatus) {
        setLookupNotice(
          "Repository ownership was verified, but the record is missing its generation status."
        );
      } else {
        setLookupNotice(
          `Repository ownership verified. The backend record status is “${parsed.approvalStatus ?? "not provided"}”.`
        );
      }
    } catch (error: unknown) {
      if (
        requestId === lookupRequest.current &&
        !controller.signal.aborted
      ) {
        setLookupError(safeErrorMessage(error));
      }
    } finally {
      if (requestId === lookupRequest.current) {
        setIsLookingUp(false);
        lookupController.current = null;
      }
    }
  }

  const usableMarkdown =
    snapshot?.generatedMarkdown?.trim() &&
    (snapshot.generationStatus === "complete" ||
      snapshot.generationStatus === "partial")
      ? snapshot.generatedMarkdown
      : null;
  const hasPartialResults =
    snapshot?.generationStatus === "partial" ||
    Boolean(snapshot?.errors.length);

  if (!selectedPath) {
    return (
      <section className="mx-auto max-w-5xl">
        <PageHeading />
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-7 text-center shadow-sm">
          <FileText
            aria-hidden="true"
            size={28}
            className="mx-auto text-slate-400"
          />
          <h2 className="mt-3 text-lg font-semibold text-slate-900">
            Select a repository to generate documentation
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600">
            Select a repository to begin.
          </p>
          <Link
            href="/repository"
            className="mt-5 inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white outline-none hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2"
          >
            <ArrowLeft aria-hidden="true" size={16} />
            Select repository
          </Link>
        </div>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeading />

      <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:flex sm:items-center sm:justify-between sm:gap-5 sm:p-6">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            Selected repository
          </p>
          <p className="mt-1 break-all font-mono text-sm text-slate-900">
            {selectedPath}
          </p>
        </div>
        <Link
          href="/analysis"
          className="mt-4 inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 sm:mt-0"
        >
          <ArrowLeft aria-hidden="true" size={16} />
          Repository Analysis
        </Link>
      </section>

      <details className="mb-5 rounded-xl border border-cyan-100 bg-cyan-50 p-4 text-sm leading-6 text-cyan-950">
        <summary className="cursor-pointer font-semibold">About generation</summary>
        <p className="mt-1">
          This page uses FastAPI and the backend-configured Groq cloud model.
          There is no separate model health endpoint in this flow; availability
          is determined by a generation request you explicitly start. Requests
          can take several minutes. No automatic health check or generation runs
          on page load.
        </p>
      </details>

      <p className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        Generation sends selected source code and documentation context to Groq
        for processing. Review your repository data before generating.
      </p>

      <form
        onSubmit={submitGeneration}
        noValidate
        className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"
      >
        <div className="mb-5">
          <div id="generation-configuration" />
          <h2 className="text-lg font-semibold text-slate-950">
            Generation configuration
          </h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Choose a repository-relative target explicitly. No file is created
            or changed by this preview request.
          </p>
        </div>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(16rem,0.7fr)]">
          <div>
            <label
              htmlFor="generation-target"
              className="mb-2 block text-sm font-medium text-slate-800"
            >
              Target Markdown path
            </label>
            <input
              id="generation-target"
              type="text"
              value={targetPath}
              onChange={(event) => setTargetPath(event.target.value)}
              placeholder="For example, docs/API.md"
              autoComplete="off"
              disabled={isGenerating}
              aria-describedby="generation-target-help"
              className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10 disabled:cursor-not-allowed disabled:bg-slate-100"
            />
            <p id="generation-target-help" className="mt-2 text-xs leading-5 text-slate-500">
              Manually enter a relative .md path. This avoids silently using the
              backend fallback target when no unambiguous target is selected.
            </p>
          </div>

          <div>
            <label
              htmlFor="max-methods"
              className="mb-2 block text-sm font-medium text-slate-800"
            >
              Maximum missing methods
              <span className="font-normal text-slate-500"> (optional)</span>
            </label>
            <input
              id="max-methods"
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              value={maxMethods}
              onChange={(event) => setMaxMethods(event.target.value)}
              placeholder="No limit"
              disabled={isGenerating}
              className="min-h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10 disabled:cursor-not-allowed disabled:bg-slate-100"
            />
            <p className="mt-2 text-xs leading-5 text-slate-500">
              When provided, this positive integer caps missing method
              documentation; it does not cap class descriptions.
            </p>
          </div>
        </div>

        <label className="mt-5 flex min-h-11 cursor-pointer items-start gap-3 text-sm text-slate-800">
          <input
            type="checkbox"
            checked={includeOverview}
            onChange={(event) => setIncludeOverview(event.target.checked)}
            disabled={isGenerating}
            className="mt-1 size-4 rounded border-slate-300 accent-cyan-700 focus-visible:ring-2 focus-visible:ring-cyan-600"
          />
          <span>
            Include a source-grounded repository overview
            <span className="mt-1 block text-xs leading-5 text-slate-500">
              Enabled by default, matching the backend request model.
            </span>
          </span>
        </label>

        {formError && (
          <div className="mt-5">
            <ErrorPanel title="Check generation settings" message={formError} />
          </div>
        )}
        {generationError && (
          <div className="mt-5">
            <ErrorPanel
              title="Generation request failed"
              message={generationError}
            />
          </div>
        )}

        <div className="mt-6 flex flex-col gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-2xl text-xs leading-5 text-slate-500">
            Generation may persist a pending preview and update the
            repository-scoped search index. It does not write source or Markdown
            files.
          </p>
          <button
            type="submit"
            disabled={isGenerating || isLookingUp}
            className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white outline-none hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70"
          >
            {isGenerating ? (
              <>
                <LoaderCircle
                  aria-hidden="true"
                  size={17}
                  className="animate-spin"
                />
                Generating preview…
              </>
            ) : (
              <>
                <Sparkles aria-hidden="true" size={17} />
                Generate preview
              </>
            )}
          </button>
        </div>
        {isGenerating && (
          <p role="status" className="mt-4 text-sm leading-6 text-cyan-800">
            The backend is analyzing repository code and requesting Groq
            generation. This may take several minutes; no percentage estimate
            is available.
          </p>
        )}
      </form>

      <section id="retrieve-preview" className="mb-6 scroll-mt-24 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">
            Retrieve a persisted preview
          </h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Enter a generation ID to review a saved preview.
          </p>
        </div>
        <form
          onSubmit={lookupGeneration}
          className="mt-4 flex flex-col gap-3 sm:flex-row"
        >
          <label htmlFor="generation-id" className="sr-only">
            Generation ID
          </label>
          <input
            id="generation-id"
            type="text"
            value={generationIdInput}
            onChange={(event) => setGenerationIdInput(event.target.value)}
            placeholder="Generation ID"
            autoComplete="off"
            disabled={isLookingUp || isGenerating}
            className="min-h-11 min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10 disabled:bg-slate-100"
          />
          <button
            type="submit"
            disabled={isLookingUp || isGenerating}
            className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70"
          >
            {isLookingUp ? (
              <LoaderCircle
                aria-hidden="true"
                size={16}
                className="animate-spin"
              />
            ) : (
              <Search aria-hidden="true" size={16} />
            )}
            Retrieve preview
          </button>
        </form>
        {isLookingUp && (
          <p role="status" className="mt-3 text-sm text-slate-600">
            Retrieving and verifying repository ownership…
          </p>
        )}
        {lookupError && (
          <div className="mt-4">
            <ErrorPanel title="Could not retrieve preview" message={lookupError} />
          </div>
        )}
        {lookupNotice && (
          <p
            role="status"
            className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900"
          >
            {lookupNotice}
          </p>
        )}
      </section>

      {snapshot && (
        <div className="space-y-6">
          <div
            role="status"
            className={`rounded-xl border px-4 py-3 text-sm leading-6 ${
              snapshot.generationStatus === "complete" && usableMarkdown
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-amber-200 bg-amber-50 text-amber-950"
            }`}
          >
            <p className="font-semibold">
              {snapshot.source === "retrieved"
                ? "Persisted preview retrieved"
                : "Generation response received"}
            </p>
            <p className="mt-1">
              {generationNotice ||
                lookupNotice ||
                "Review the backend status and details below."}
            </p>
          </div>

          <GenerationMetadata snapshot={snapshot} />

          {verifiedRecord && verifiedRecord.status === "pending" && (
            <a href="#generation-review-heading" className="inline-flex min-h-11 items-center rounded-lg bg-slate-900 px-4 text-sm font-semibold text-white hover:bg-slate-700">
              Continue to review
            </a>
          )}
          {lookupNotice && (
            <p
              role="status"
              className="rounded-xl border border-cyan-100 bg-cyan-50 px-4 py-3 text-sm leading-6 text-cyan-950"
            >
              {lookupNotice}
            </p>
          )}

          {verifiedRecord &&
            snapshot.generationId === verifiedRecord.generation_id && (
              <GenerationReviewPanel
                key={verifiedRecord.generation_id}
                initialRecord={verifiedRecord}
                repositoryPath={selectedPath}
                generatedMarkdown={snapshot.generatedMarkdown ?? ""}
                verifyRepositoryIdentity={getWindowsRepositoryIdentity}
                onRecordUpdated={(record) => {
                  setVerifiedRecord(record);
                  setSnapshot((current) =>
                    current
                      ? {
                          ...current,
                          generatedMarkdown: record.generated_markdown,
                          approvalStatus: record.status,
                          documentationTarget: record.documentation_target,
                          targetHash: record.target_hash_before,
                          sourceHashes: parseStringRecord(record.source_hashes),
                          generationStatus: record.generation_status,
                        }
                      : current
                  );
                }}
              />
            )}

          {snapshot.errors.length > 0 && (
            <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5 sm:p-6">
              <h2 className="text-base font-semibold text-amber-950">
                Backend-reported warnings and errors
              </h2>
              <ul className="mt-3 space-y-3">
                {snapshot.errors.map((error, index) => (
                  <li
                    key={`${error.stage}-${error.file ?? "repository"}-${index}`}
                    className="rounded-lg border border-amber-200 bg-white/70 p-3 text-sm leading-6 text-amber-950"
                  >
                    <p className="font-medium">{error.stage}</p>
                    {error.file && (
                      <p className="font-mono text-xs">{error.file}</p>
                    )}
                    <p className="mt-1 break-words">{error.message}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <RagRetrievalDetails retrieval={snapshot.retrieval} />

          {usableMarkdown ? (
            <GeneratedDocumentationPreview
              key={`${snapshot.generationId ?? snapshot.documentationTarget ?? "preview"}-${snapshot.source}`}
              markdown={usableMarkdown}
              partial={hasPartialResults}
            />
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-sm leading-6 text-slate-600">
              No usable generated Markdown was returned for this record. The
              status and any backend-reported errors above are the authoritative
              result; no successful preview is shown.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PageHeading() {
  return (
    <header className="mb-7">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">
        Cloud AI
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
        AI Documentation
      </h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
        Generate source-grounded documentation previews with the backend’s
        Groq model. Generation does not approve or write documentation files.
      </p>
    </header>
  );
}

function GenerationMetadata({
  snapshot,
}: {
  snapshot: GenerationSnapshot;
}) {
  const hashEntries = Object.entries(snapshot.sourceHashes);
  const metadata = [
    ["Generation ID", snapshot.generationId],
    ["Repository", snapshot.repository],
    ["Selected path", snapshot.repositoryPath],
    ["Target documentation", snapshot.documentationTarget],
    ["Generation status", snapshot.generationStatus],
    ["Approval status", snapshot.approvalStatus],
    ["Created at", snapshot.createdAt],
    ["Generated classes", snapshot.generatedClassCount],
    ["Generated methods", snapshot.generatedMethodCount],
    ["Skipped documented methods", snapshot.skippedMethodCount],
    [
      "Maximum methods option",
      snapshot.source === "retrieved"
        ? "Not persisted by backend"
        : snapshot.maxMethodsRequested ?? "Not supplied",
    ],
    ["Target hash at generation", snapshot.targetHash],
  ] as const;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">
            Generation details
          </h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Source and target hashes are recorded so a later approval workflow
            can detect changes. A pending status records a preview; it does not
            mean the target file was updated.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {snapshot.generationStatus && (
            <StatusPill>{snapshot.generationStatus}</StatusPill>
          )}
          {snapshot.approvalStatus && (
            <StatusPill>{snapshot.approvalStatus}</StatusPill>
          )}
          {snapshot.source === "retrieved" && (
            <StatusPill>repository identity verified</StatusPill>
          )}
        </div>
      </div>

      <dl className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {metadata.map(([label, value]) => (
          <div
            key={label}
            className="min-w-0 rounded-lg border border-slate-100 bg-slate-50 p-3"
          >
            <dt className="text-xs font-medium text-slate-500">{label}</dt>
            <dd className="mt-1 break-all text-sm text-slate-900">
              {value === null || value === undefined || value === ""
                ? "Not available"
                : typeof value === "number"
                  ? value
                  : value}
            </dd>
          </div>
        ))}
      </dl>

      <details className="mt-4 rounded-lg border border-slate-200">
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-slate-800 outline-none focus-visible:ring-2 focus-visible:ring-cyan-600">
          Source hashes ({hashEntries.length})
        </summary>
        {hashEntries.length > 0 ? (
          <ul className="max-h-72 overflow-auto border-t border-slate-200">
            {hashEntries.slice(0, 100).map(([file, hash]) => (
              <li
                key={file}
                className="grid gap-1 border-b border-slate-100 px-4 py-3 last:border-b-0 sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] sm:gap-4"
              >
                <span className="break-all font-mono text-xs text-slate-700">
                  {file}
                </span>
                <span className="break-all font-mono text-xs text-slate-500">
                  {hash}
                </span>
              </li>
            ))}
            {hashEntries.length > 100 && (
              <li className="px-4 py-3 text-xs text-slate-600">
                Showing the first 100 of {hashEntries.length} source hashes.
              </li>
            )}
          </ul>
        ) : (
          <p className="border-t border-slate-200 px-4 py-3 text-sm text-slate-600">
            Source hashes were not included in this response.
          </p>
        )}
      </details>

      {snapshot.targetHash === "__missing__" && (
        <p className="mt-3 text-xs leading-5 text-slate-600">
          The backend reports that the selected target did not exist when this
          generation was created.
        </p>
      )}
    </section>
  );
}

function RagRetrievalDetails({
  retrieval,
}: {
  retrieval: RetrievalSummary | null;
}) {
  if (!retrieval) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-950">
          Repository context retrieval
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          The backend response did not include retrieval metadata. RAG usage
          cannot be confirmed for this result.
        </p>
      </section>
    );
  }

  const status = (value: boolean | undefined) =>
    value === undefined ? "Not reported" : value ? "Yes" : "No";
  const details = [
    ["Strategy", retrieval.strategy],
    ["Repository-scoped", status(retrieval.repository_scoped)],
    ["Vector store used", status(retrieval.vector_store_used)],
    ["Local Markdown fallback used", status(retrieval.fallback_used)],
    ["Fallback count", retrieval.fallback_count],
    ["Retrieval query count", retrieval.query_count],
    ["Retrieved chunk count", retrieval.retrieved_chunks],
  ] as const;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <h2 className="text-lg font-semibold text-slate-950">
        Repository context retrieval
      </h2>
      <p className="mt-1 text-sm leading-6 text-slate-600">
        Counts and strategy are reported by the backend. The generation
        response does not return retrieved text, source Markdown paths, or
        context-character totals, so none are inferred here. Vector-store
        distances, when used internally, are not confidence percentages.
      </p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {details.map(([label, value]) => (
          <div
            key={label}
            className="min-w-0 rounded-lg border border-slate-100 bg-slate-50 p-3"
          >
            <dt className="text-xs font-medium text-slate-500">{label}</dt>
            <dd className="mt-1 break-words text-sm text-slate-900">
              {value === null || value === undefined ? "Not available" : value}
            </dd>
          </div>
        ))}
      </dl>

      {retrieval.indexing && (
        <div className="mt-4 rounded-xl border border-cyan-100 bg-cyan-50 p-4">
          <h3 className="text-sm font-semibold text-cyan-950">
            Backend documentation indexing during generation
          </h3>
          <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {Object.entries(retrieval.indexing).map(([key, value]) => (
              <div key={key}>
                <dt className="text-xs text-cyan-800">{key.replaceAll("_", " ")}</dt>
                <dd className="mt-1 text-sm font-semibold text-cyan-950">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs leading-5 text-cyan-900">
            This is the backend’s internal index operation. It does not write
            repository Markdown files.
          </p>
        </div>
      )}

      {retrieval.errors && retrieval.errors.length > 0 && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h3 className="text-sm font-semibold text-amber-950">
            Retrieval or indexing warnings
          </h3>
          <ul className="mt-2 space-y-2">
            {retrieval.errors.map((error, index) => (
              <li
                key={`${error.stage}-${index}`}
                className="text-sm leading-6 text-amber-900"
              >
                <span className="font-medium">{error.stage}: </span>
                {error.message}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
