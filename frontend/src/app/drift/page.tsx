"use client";

import {
  AlertTriangle,
  BookOpenCheck,
  GitBranch,
  LoaderCircle,
  Search,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import AnalysisErrorPanel from "../components/repository/AnalysisErrorPanel";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";
import DocumentationCoverageSummary from "../components/documentation/DocumentationCoverageSummary";
import DocumentationFiles from "../components/documentation/DocumentationFiles";
import DetectedDocumentationDrift from "../components/documentation/DetectedDocumentationDrift";
import {
  MappingStatusLists,
  MissingDocumentationList,
} from "../components/documentation/DocumentationFindings";
import {
  analyzeFullRepository,
  analyzeRepository,
  getApiErrorMessage,
} from "@/lib/api";
import type {
  AnalysisError,
  ClassCoverage,
  CoverageSummary,
  DocumentationFinding,
  FullAnalyzeResponse,
  AnalyzeResponse,
} from "@/types/api";

interface DocumentationCoverageView {
  summary: Partial<CoverageSummary>;
  classes: ClassCoverage[];
  missingFindings: DocumentationFinding[];
  ambiguousFindings: DocumentationFinding[];
  unsupportedFindings: DocumentationFinding[];
  emptyFindings: DocumentationFinding[];
  findings: DocumentationFinding[];
  targets: string[];
  documentationFiles: string[];
  missingFindingsAvailable: boolean;
  ambiguousFindingsAvailable: boolean;
  emptyFindingsAvailable: boolean;
  classesAvailable: boolean;
  targetsAvailable: boolean;
  documentationFilesAvailable: boolean;
  errors: AnalysisError[];
  schemaWarnings: string[];
}

interface CompletedAnalysis {
  repositoryPath: string;
  repositoryName: string | null;
  analyzedAt: string;
  coverage: DocumentationCoverageView;
}

const summaryKeys: Array<keyof CoverageSummary> = [
  "java_file_count",
  "class_count",
  "method_count",
  "documented_class_count",
  "missing_class_count",
  "ambiguous_class_count",
  "unsupported_class_count",
  "documented_method_count",
  "missing_method_count",
  "ambiguous_method_count",
  "unsupported_method_count",
  "documentation_file_count",
  "empty_documentation_file_count",
];

const coverageStatuses = new Set([
  "documented",
  "missing",
  "ambiguous",
  "unsupported",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function normalizeErrors(value: unknown): AnalysisError[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (
      !isRecord(item) ||
      typeof item.stage !== "string" ||
      typeof item.message !== "string"
    ) {
      return [];
    }
    const message = item.message.includes("Traceback (most recent call last):")
      ? "The backend reported an internal error. See the backend logs for details."
      : item.message;
    return [
      {
        stage: item.stage,
        message,
        file:
          typeof item.file === "string" || item.file === null
            ? item.file
            : undefined,
      },
    ];
  });
}

function normalizeFinding(value: unknown): DocumentationFinding | null {
  if (!isRecord(value) || typeof value.finding_type !== "string") {
    return null;
  }
  const finding: DocumentationFinding = {
    finding_type: value.finding_type,
  };
  for (const key of [
    "source_file",
    "documentation_file",
    "class",
    "method",
    "signature",
    "documentation_target",
    "reason",
    "review_classification",
  ] as const) {
    const field = value[key];
    if (typeof field === "string") {
      finding[key] = field;
    } else if (field === null && key !== "review_classification") {
      finding[key] = null;
    }
  }
  if (isRecord(value.evidence)) {
    finding.evidence = value.evidence;
  }
  if (isRecord(value.source_line_range)) {
    const startLine = value.source_line_range.start_line;
    const endLine = value.source_line_range.end_line;
    finding.source_line_range = {
      ...(typeof startLine === "number" ? { start_line: startLine } : {}),
      ...(typeof endLine === "number" ? { end_line: endLine } : {}),
    };
  }
  return finding;
}

function normalizeClasses(value: unknown): ClassCoverage[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.flatMap((item) => {
    if (
      !isRecord(item) ||
      typeof item.source_file !== "string" ||
      typeof item.class !== "string" ||
      typeof item.coverage !== "string" ||
      !coverageStatuses.has(item.coverage)
    ) {
      return [];
    }
    const methods = Array.isArray(item.methods)
      ? item.methods.flatMap((method) => {
          if (
            !isRecord(method) ||
            typeof method.method !== "string" ||
            typeof method.signature !== "string" ||
            typeof method.coverage !== "string" ||
            !coverageStatuses.has(method.coverage)
          ) {
            return [];
          }
          return [
            {
              method: method.method,
              signature: method.signature,
              coverage: method.coverage,
              documentation_file: optionalString(method.documentation_file),
            },
          ];
        })
      : [];
    return [
      {
        source_file: item.source_file,
        class: item.class,
        package: optionalString(item.package),
        coverage: item.coverage,
        documentation_file: optionalString(item.documentation_file),
        methods,
      },
    ];
  });
}

function normalizeCoverage(
  response: FullAnalyzeResponse
): DocumentationCoverageView {
  const warnings: string[] = [];
  const data: unknown = response.documentation_analysis;
  if (!isRecord(data)) {
    return {
      summary: {},
      classes: [],
      missingFindings: [],
      ambiguousFindings: [],
      unsupportedFindings: [],
      emptyFindings: [],
      findings: [],
      targets: [],
      documentationFiles: stringArray(response.documentation_files),
      missingFindingsAvailable: false,
      ambiguousFindingsAvailable: false,
      emptyFindingsAvailable: false,
      classesAvailable: false,
      targetsAvailable: false,
      documentationFilesAvailable: Array.isArray(
        response.documentation_files
      ),
      errors: normalizeErrors(response.errors),
      schemaWarnings: [
        "The response did not contain a valid documentation_analysis object.",
      ],
    };
  }

  const rawSummary = data.summary;
  const summary: Partial<CoverageSummary> = {};
  if (isRecord(rawSummary)) {
    let availableSummaryCount = 0;
    for (const key of summaryKeys) {
      const count = rawSummary[key];
      if (typeof count === "number" && Number.isFinite(count)) {
        summary[key] = count;
        availableSummaryCount += 1;
      }
    }
    if (availableSummaryCount < summaryKeys.length) {
      warnings.push("One or more coverage counts were unavailable.");
    }
  } else {
    warnings.push("Coverage summary was missing or malformed.");
  }

  const parseFindings = (value: unknown, fieldName: string) => {
    if (!Array.isArray(value)) {
      warnings.push(`${fieldName} was not included or malformed.`);
      return { values: [] as DocumentationFinding[], available: false };
    }
    const values = value
      .map(normalizeFinding)
      .filter(
        (finding): finding is DocumentationFinding => finding !== null
      );
    if (values.length < value.length) {
      warnings.push(`${fieldName} contained entries with an invalid shape.`);
    }
    return { values, available: true };
  };

  const classes = normalizeClasses(data.classes);
  if (!Array.isArray(data.classes)) {
    warnings.push("Class and method mapping details were unavailable.");
  } else if (classes.length < data.classes.length) {
    warnings.push("Some class mapping entries had an invalid shape.");
  }
  const missingFindings = parseFindings(
    data.missing_documentation_findings,
    "Missing-documentation findings"
  );
  const ambiguousFindings = parseFindings(
    data.ambiguous_mappings,
    "Ambiguous mapping findings"
  );
  const emptyFindings = parseFindings(
    data.empty_documentation_findings,
    "Empty-documentation findings"
  );
  const documentationFilesAvailable = Array.isArray(
    response.documentation_files
  );
  const targetsAvailable = Array.isArray(
    data.proposed_documentation_targets
  );
  const allFindings = parseFindings(data.findings, "All coverage findings");
  const unsupportedFindings = allFindings.values.filter((finding) =>
    classes.some(
      (classInfo) =>
        classInfo.source_file === finding.source_file &&
        classInfo.class === finding.class &&
        ((classInfo.coverage === "unsupported" && !finding.method) ||
          classInfo.methods.some(
            (method) =>
              method.coverage === "unsupported" &&
              method.method === finding.method
          ))
    )
  );
  if (!documentationFilesAvailable) {
    warnings.push("The documentation file list was unavailable.");
  }
  if (!targetsAvailable) {
    warnings.push("Proposed documentation targets were unavailable.");
  }

  return {
    summary,
    classes,
    missingFindings: missingFindings.values,
    ambiguousFindings: ambiguousFindings.values,
    unsupportedFindings,
    emptyFindings: emptyFindings.values,
    findings: allFindings.values,
    targets: stringArray(data.proposed_documentation_targets),
    documentationFiles: stringArray(response.documentation_files),
    missingFindingsAvailable: missingFindings.available,
    ambiguousFindingsAvailable: ambiguousFindings.available,
    emptyFindingsAvailable: emptyFindings.available,
    classesAvailable: Array.isArray(data.classes),
    targetsAvailable,
    documentationFilesAvailable,
    errors: [
      ...new Map(
        [...normalizeErrors(response.errors), ...normalizeErrors(data.errors)].map(
          (error) => [
            `${error.stage}\u0000${error.file ?? ""}\u0000${error.message}`,
            error,
          ]
        )
      ).values(),
    ],
    schemaWarnings: warnings,
  };
}

function isAbsoluteWindowsPath(path: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(path) || /^\\\\[^\\]+\\[^\\]+/.test(path);
}

export default function DocumentationDriftPage() {
  const { repositoryPath } = useRepositoryAnalysis();
  return (
    <DocumentationDriftContent
      key={repositoryPath}
      repositoryPath={repositoryPath}
    />
  );
}

function DocumentationDriftContent({
  repositoryPath,
}: {
  repositoryPath: string;
}) {
  const [loadingPath, setLoadingPath] = useState<string | null>(null);
  const [validationError, setValidationError] = useState("");
  const [requestError, setRequestError] = useState("");
  const [analysis, setAnalysis] = useState<CompletedAnalysis | null>(null);
  const [driftLoadingPath, setDriftLoadingPath] = useState<string | null>(null);
  const [driftError, setDriftError] = useState("");
  const [gitDrift, setGitDrift] = useState<{
    repositoryPath: string;
    analyzedAt: string;
    data: AnalyzeResponse;
  } | null>(null);
  const latestRequest = useRef(0);
  const latestDriftRequest = useRef(0);
  const selectedPath = repositoryPath.trim();
  const visibleAnalysis =
    analysis?.repositoryPath === selectedPath ? analysis : null;
  const visibleGitDrift =
    gitDrift?.repositoryPath === selectedPath ? gitDrift : null;
  const loading = loadingPath === selectedPath;
  const driftLoading = driftLoadingPath === selectedPath;

  useEffect(() => {
    return () => {
      latestRequest.current += 1;
      latestDriftRequest.current += 1;
    };
  }, [selectedPath]);

  async function runAnalysis() {
    const requestId = ++latestRequest.current;
    const path = selectedPath;
    setValidationError("");
    setRequestError("");
    setAnalysis(null);
    setGitDrift(null);
    setDriftError("");

    if (!path) {
      setValidationError("Select a repository in Repository Analysis first.");
      return;
    }
    if (!isAbsoluteWindowsPath(path)) {
      setValidationError(
        "The selected path is not an absolute Windows filesystem path. Update it in Repository Analysis."
      );
      return;
    }

    setLoadingPath(path);
    try {
      const response = await analyzeFullRepository(path);
      if (requestId !== latestRequest.current) {
        return;
      }
      if (!isRecord(response)) {
        setRequestError("The backend returned an invalid analysis response.");
        return;
      }
      const coverage = normalizeCoverage(response);
      setAnalysis({
        repositoryPath: path,
        repositoryName:
          typeof response.repository === "string"
            ? response.repository
            : null,
        analyzedAt: new Date().toLocaleString(),
        coverage,
      });
    } catch (error: unknown) {
      if (requestId === latestRequest.current) {
        const message = getApiErrorMessage(error);
        setRequestError(
          message.includes("Traceback (most recent call last):")
            ? "The backend reported an internal error. See the backend logs for details."
            : message
        );
      }
    } finally {
      if (requestId === latestRequest.current) {
        setLoadingPath(null);
      }
    }
  }

  async function runGitDriftAnalysis() {
    const requestId = ++latestDriftRequest.current;
    const path = selectedPath;
    setDriftError("");
    setGitDrift(null);

    if (!path) {
      setDriftError("Select a repository in Repository Analysis first.");
      return;
    }
    if (!isAbsoluteWindowsPath(path)) {
      setDriftError(
        "The selected path is not an absolute Windows filesystem path. Update it in Repository Analysis."
      );
      return;
    }

    setDriftLoadingPath(path);
    try {
      const data = await analyzeRepository({
        repository_path: path,
        mode: "working_tree",
      });
      if (requestId === latestDriftRequest.current) {
        setGitDrift({
          repositoryPath: path,
          analyzedAt: new Date().toLocaleString(),
          data,
        });
      }
    } catch (error: unknown) {
      if (requestId === latestDriftRequest.current) {
        const message = getApiErrorMessage(error);
        setDriftError(
          message.includes("Traceback (most recent call last):")
            ? "The backend reported an internal error. See the backend logs for details."
            : message
        );
      }
    } finally {
      if (requestId === latestDriftRequest.current) {
        setDriftLoadingPath(null);
      }
    }
  }

  const hasPartialErrors = Boolean(
    visibleAnalysis?.coverage.errors.length ||
      visibleAnalysis?.coverage.schemaWarnings.length
  );
  const knownDocumentationFileCount =
    visibleAnalysis?.coverage.summary.documentation_file_count;
  const discoveredDocumentationFiles =
    visibleAnalysis?.coverage.documentationFiles.length ?? 0;
  const hasNoDocumentationFiles =
    visibleAnalysis !== null &&
    (knownDocumentationFileCount === 0 ||
      (visibleAnalysis.coverage.documentationFilesAvailable &&
        knownDocumentationFileCount === undefined &&
        discoveredDocumentationFiles === 0));

  return (
    <div className="mx-auto max-w-7xl">
      <header className="mb-7">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">
          Documentation quality
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
          Documentation Coverage
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Review coverage and check Git drift separately.
        </p>
      </header>

      {!selectedPath ? (
        <section className="rounded-2xl border border-dashed border-slate-300 bg-white p-7 text-center shadow-sm">
          <BookOpenCheck
            aria-hidden="true"
            size={26}
            className="mx-auto text-slate-400"
          />
          <h2 className="mt-3 text-base font-semibold text-slate-900">
            Select a repository to review coverage
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">
            Select a repository to begin.
          </p>
          <Link
            href="/repository"
            className="mt-5 inline-flex min-h-10 items-center justify-center rounded-lg bg-slate-900 px-4 text-sm font-medium text-white outline-none hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2"
          >
            Select repository
          </Link>
        </section>
      ) : (
        <>
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
                  Selected repository
                </p>
                <p className="mt-1 break-all font-mono text-sm text-slate-900">
                  {selectedPath}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  A fresh full analysis runs only when you choose the button.
                </p>
              </div>
              <button
                type="button"
                onClick={runAnalysis}
                disabled={loading}
                className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white outline-none hover:bg-slate-700 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70"
              >
                {loading ? (
                  <>
                    <LoaderCircle
                      aria-hidden="true"
                      size={17}
                      className="animate-spin"
                    />
                    Analyzing documentation…
                  </>
                ) : (
                  <>
                    <Search aria-hidden="true" size={16} />
                    Analyze documentation
                  </>
                )}
              </button>
            </div>
          </section>

          {validationError && (
            <div className="mt-5">
              <AnalysisErrorPanel
                title="Repository selection needed"
                message={validationError}
              />
            </div>
          )}
          {requestError && (
            <div className="mt-5">
              <AnalysisErrorPanel
                title="Documentation analysis failed"
                message={requestError}
              />
            </div>
          )}
          {loading && (
            <div
              role="status"
              aria-live="polite"
              className="mt-5 rounded-xl border border-cyan-100 bg-cyan-50 p-4 text-sm text-cyan-950"
            >
              The local backend is scanning Java and documentation files.
            </div>
          )}

          {visibleAnalysis && (
            <div className="mt-7 space-y-7">
              {hasPartialErrors && (
                <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
                  <AlertTriangle
                    aria-hidden="true"
                    size={18}
                    className="mt-0.5 shrink-0"
                  />
                  <div>
                    <p className="font-semibold">
                      Analysis completed with limitations
                    </p>
                    <p className="mt-1 leading-5">
                      The backend returned analysis errors or incomplete
                      optional details. Available coverage is shown below.
                    </p>
                  </div>
                </div>
              )}

              <section className="rounded-xl border border-slate-200 bg-white px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                  Analysis run
                </p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {visibleAnalysis.repositoryName ?? "Repository name not available"}
                </p>
                <p className="mt-1 break-all font-mono text-xs text-slate-600">
                  {visibleAnalysis.repositoryPath}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  Completed {visibleAnalysis.analyzedAt}
                </p>
              </section>

              <DocumentationCoverageSummary
                summary={visibleAnalysis.coverage.summary}
              />
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cyan-100 bg-cyan-50 p-4">
                <p className="text-sm text-cyan-950">Ready to address missing documentation?</p>
                <Link href="/ai-documentation" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700">Generate preview</Link>
              </div>

              {visibleAnalysis.coverage.summary.java_file_count === 0 && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                  The backend found no Java files in this repository. Coverage
                  is shown as returned; there are no Java classes or methods to
                  map.
                </div>
              )}

              {hasNoDocumentationFiles && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                  No Markdown or other supported documentation files were
                  discovered. Coverage findings and recommendations below are
                  reported by the backend.
                </div>
              )}

              <MissingDocumentationList
                findings={visibleAnalysis.coverage.missingFindings}
                available={
                  visibleAnalysis.coverage.missingFindingsAvailable
                }
              />

              <MappingStatusLists
                classes={visibleAnalysis.coverage.classes}
                ambiguousFindings={visibleAnalysis.coverage.ambiguousFindings}
                unsupportedFindings={
                  visibleAnalysis.coverage.unsupportedFindings
                }
                available={visibleAnalysis.coverage.classesAvailable}
              />

              <DocumentationFiles
                files={visibleAnalysis.coverage.documentationFiles}
                emptyFindings={visibleAnalysis.coverage.emptyFindings}
                errors={visibleAnalysis.coverage.errors}
                targets={visibleAnalysis.coverage.targets}
                filesAvailable={
                  visibleAnalysis.coverage.documentationFilesAvailable
                }
                targetsAvailable={visibleAnalysis.coverage.targetsAvailable}
                emptyFindingsAvailable={
                  visibleAnalysis.coverage.emptyFindingsAvailable
                }
              />

              <section
                aria-labelledby="detected-drift-heading"
                className="rounded-xl border border-slate-200 bg-slate-50 p-5 sm:p-6"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2
                      id="detected-drift-heading"
                      className="text-base font-semibold text-slate-900"
                    >
                      Detected documentation drift
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                      Full analysis reports coverage only. To see genuine
                      change-linked drift, explicitly run the backend&apos;s
                      read-only Git working-tree comparison.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={runGitDriftAnalysis}
                    disabled={driftLoading}
                    className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 outline-none hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70"
                  >
                    {driftLoading ? (
                      <>
                        <LoaderCircle
                          aria-hidden="true"
                          size={16}
                          className="animate-spin"
                        />
                        Checking changes…
                      </>
                    ) : (
                      <>
                        <GitBranch aria-hidden="true" size={16} />
                        Check working-tree drift
                      </>
                    )}
                  </button>
                </div>
                {driftLoading && (
                  <p role="status" aria-live="polite" className="mt-3 text-xs text-slate-600">
                    The backend is comparing Java files with the Git working
                    tree.
                  </p>
                )}
                {driftError && (
                  <div className="mt-4">
                    <AnalysisErrorPanel
                      title="Git drift analysis failed"
                      message={driftError}
                    />
                  </div>
                )}
                {visibleGitDrift && (
                  <div className="mt-5">
                    {visibleGitDrift.data.results.some(
                      (file) => (file.errors?.length ?? 0) > 0
                    ) && (
                      <div className="mb-4">
                        <AnalysisErrorPanel
                          title="Git drift analysis completed with errors"
                          errors={visibleGitDrift.data.results.flatMap(
                            (file) => file.errors ?? []
                          )}
                        />
                      </div>
                    )}
                    <p className="mb-3 text-xs text-slate-500">
                      Working-tree analysis completed{" "}
                      {visibleGitDrift.analyzedAt} for{" "}
                      <span className="font-mono">
                        {visibleGitDrift.repositoryPath}
                      </span>
                    </p>
                    <DetectedDocumentationDrift result={visibleGitDrift.data} />
                  </div>
                )}
              </section>

              <AnalysisErrorPanel
                title="Documentation analysis errors"
                errors={visibleAnalysis.coverage.errors}
              />
              {visibleAnalysis.coverage.schemaWarnings.length > 0 && (
                <AnalysisErrorPanel
                  title="Some response details were unavailable"
                  errors={visibleAnalysis.coverage.schemaWarnings.map(
                    (message) => ({
                      stage: "response_validation",
                      message,
                    })
                  )}
                />
              )}
            </div>
          )}

          {!visibleAnalysis && !loading && !requestError && !validationError && (
            <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-5 py-6 text-center">
              <p className="text-sm font-medium text-slate-700">
                No coverage analysis has been run for this repository.
              </p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Select “Analyze documentation” to request a fresh read-only
                analysis.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
