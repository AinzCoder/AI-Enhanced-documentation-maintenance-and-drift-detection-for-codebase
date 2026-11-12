"use client";

import { ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import type {
  ClassCoverage,
  DocumentationFinding,
} from "@/types/api";

const PAGE_SIZE = 20;

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function evidenceList(finding: DocumentationFinding, key: string): string[] {
  const evidence = finding.evidence;
  if (typeof evidence !== "object" || evidence === null) {
    return [];
  }
  const value = (evidence as Record<string, unknown>)[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function evidenceString(
  finding: DocumentationFinding,
  key: string
): string | undefined {
  const evidence = finding.evidence;
  if (typeof evidence !== "object" || evidence === null) {
    return undefined;
  }
  const value = (evidence as Record<string, unknown>)[key];
  return typeof value === "string" ? value : undefined;
}

function FindingCard({
  finding,
  index,
}: {
  finding: DocumentationFinding;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = `documentation-finding-${index}`;
  const evidenceHeadings = evidenceList(finding, "matching_headings");
  const evidenceFiles = evidenceList(finding, "documentation_files");
  const expectedSignature = evidenceString(finding, "expected_signature");
  const reason = text(finding.reason);
  const method = text(finding.method);
  const signature = text(finding.signature);

  return (
    <article className="rounded-xl border border-slate-200 bg-white">
      <div className="flex items-start gap-3 p-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-900">
              Missing documentation
            </span>
            <span className="rounded bg-slate-100 px-2 py-1 font-mono text-[11px] text-slate-700">
              {finding.finding_type}
            </span>
          </div>
          <p className="mt-2 break-all font-mono text-xs text-slate-600">
            {text(finding.source_file) ?? "Source file not provided"}
          </p>
          <p className="mt-1 text-sm font-medium text-slate-900">
            {text(finding.class) ?? "Class not provided"}
            {method ? ` · ${method}` : ""}
            {signature && signature !== method ? ` (${signature})` : ""}
          </p>
          {reason && (
            <p className="mt-1 text-sm leading-5 text-slate-600">{reason}</p>
          )}
        </div>
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={`${expanded ? "Hide" : "Show"} details for ${text(finding.class) ?? "finding"}${method ? ` ${method}` : ""}`}
          onClick={() => setExpanded((current) => !current)}
          className="flex size-9 shrink-0 items-center justify-center rounded-lg text-slate-600 outline-none hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-cyan-600"
        >
          {expanded ? (
            <ChevronDown aria-hidden="true" size={18} />
          ) : (
            <ChevronRight aria-hidden="true" size={18} />
          )}
        </button>
      </div>
      {expanded && (
        <div
          id={detailsId}
          className="space-y-3 border-t border-slate-100 bg-slate-50 px-4 py-4"
        >
          {text(finding.documentation_target) && (
            <Detail label="Suggested target">
              <span className="font-mono">
                {text(finding.documentation_target)}
              </span>
              <span className="ml-2 text-slate-500">(recommendation only)</span>
            </Detail>
          )}
          {text(finding.documentation_file) && (
            <Detail label="Mapped documentation">
              <span className="font-mono">
                {text(finding.documentation_file)}
              </span>
            </Detail>
          )}
          {expectedSignature && (
            <Detail label="Expected signature">
              <span className="font-mono">{expectedSignature}</span>
            </Detail>
          )}
          {evidenceFiles.length > 0 && (
            <Detail label="Candidate documentation files">
              {evidenceFiles.map((file) => (
                <span key={file} className="mr-2 inline-block font-mono">
                  {file}
                </span>
              ))}
            </Detail>
          )}
          {evidenceHeadings.length > 0 && (
            <Detail label="Matching headings">
              {evidenceHeadings.map((heading) => (
                <span
                  key={heading}
                  className="mr-2 inline-block rounded bg-white px-2 py-1 font-mono"
                >
                  {heading}
                </span>
              ))}
            </Detail>
          )}
          {finding.source_line_range && (
            <Detail label="Source lines">
              {finding.source_line_range.start_line ?? "?"}
              {finding.source_line_range.end_line
                ? `–${finding.source_line_range.end_line}`
                : ""}
            </Detail>
          )}
        </div>
      )}
    </article>
  );
}

function Detail({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <p className="text-xs leading-5 text-slate-700">
      <span className="mr-2 font-semibold text-slate-500">{label}:</span>
      {children}
    </p>
  );
}

export function MissingDocumentationList({
  findings,
  available = true,
}: {
  findings: DocumentationFinding[];
  available?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const types = useMemo(
    () => [...new Set(findings.map((finding) => finding.finding_type))].sort(),
    [findings]
  );
  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return findings.filter((finding) => {
      if (type && finding.finding_type !== type) {
        return false;
      }
      if (!normalizedQuery) {
        return true;
      }
      return [
        finding.source_file,
        finding.class,
        finding.method,
        finding.signature,
      ].some(
        (value) =>
          typeof value === "string" &&
          value.toLowerCase().includes(normalizedQuery)
      );
    });
  }, [findings, query, type]);

  function clearFilters() {
    setQuery("");
    setType("");
    setVisibleCount(PAGE_SIZE);
  }

  return (
    <section aria-labelledby="missing-findings-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2
            id="missing-findings-heading"
            className="text-lg font-semibold text-slate-950"
          >
            Missing documentation
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            {findings.length} backend-reported finding
            {findings.length === 1 ? "" : "s"}
          </p>
        </div>
        {(query || type) && (
          <button
            type="button"
            onClick={clearFilters}
            className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-slate-300 px-3 text-xs font-medium text-slate-700 outline-none hover:bg-white focus-visible:ring-2 focus-visible:ring-cyan-600"
          >
            <X aria-hidden="true" size={14} />
            Clear filters
          </button>
        )}
      </div>
      {findings.length > 0 && (
        <div className="mb-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,0.45fr)]">
          <div className="relative">
            <Search
              aria-hidden="true"
              size={17}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <label htmlFor="finding-search" className="sr-only">
              Search findings by file, class, or method
            </label>
            <input
              id="finding-search"
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setVisibleCount(PAGE_SIZE);
              }}
              placeholder="Search file, class, or method"
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white pl-10 pr-3 text-sm outline-none focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10"
            />
          </div>
          <div>
            <label htmlFor="finding-type-filter" className="sr-only">
              Filter by finding type
            </label>
            <select
              id="finding-type-filter"
              value={type}
              onChange={(event) => {
                setType(event.target.value);
                setVisibleCount(PAGE_SIZE);
              }}
              className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10"
            >
              <option value="">All finding types</option>
              {types.map((findingType) => (
                <option key={findingType} value={findingType}>
                  {findingType}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}
      {filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
          <p className="text-sm font-medium text-slate-700">
            {!available
              ? "Missing-documentation findings were not included in the response."
              : findings.length === 0
              ? "No missing-documentation findings."
              : "No findings match these filters."}
          </p>
          {available && findings.length === 0 && (
            <p className="mt-1 text-xs text-slate-500">
              No missing items were returned by the backend. Ambiguous and
              unsupported items are listed separately.
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {filtered.slice(0, visibleCount).map((finding, index) => (
              <FindingCard
                key={`${finding.finding_type}-${finding.source_file ?? "source"}-${finding.class ?? "class"}-${finding.method ?? "method"}-${index}`}
                finding={finding}
                index={index}
              />
            ))}
          </div>
          {filtered.length > visibleCount && (
            <button
              type="button"
              onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
              className="mt-4 min-h-10 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600"
            >
              Show more ({filtered.length - visibleCount} remaining)
            </button>
          )}
        </>
      )}
    </section>
  );
}

export function MappingStatusLists({
  classes,
  ambiguousFindings,
  unsupportedFindings = [],
  available = true,
}: {
  classes: ClassCoverage[];
  ambiguousFindings: DocumentationFinding[];
  unsupportedFindings?: DocumentationFinding[];
  available?: boolean;
}) {
  const ambiguousElements = classes.flatMap((classInfo) => [
    ...(classInfo.coverage === "ambiguous"
      ? [{ label: "Class", name: classInfo.class, file: classInfo.source_file }]
      : []),
    ...classInfo.methods
      .filter((method) => method.coverage === "ambiguous")
      .map((method) => ({
        label: "Method",
        name: `${classInfo.class}.${method.signature}`,
        file: classInfo.source_file,
      })),
  ]);
  const unsupportedElements = classes.flatMap((classInfo) => [
    ...(classInfo.coverage === "unsupported"
      ? [{ label: "Class", name: classInfo.class, file: classInfo.source_file }]
      : []),
    ...classInfo.methods
      .filter((method) => method.coverage === "unsupported")
      .map((method) => ({
        label: "Method",
        name: `${classInfo.class}.${method.signature}`,
        file: classInfo.source_file,
      })),
  ]);
  const documentedElements = classes.flatMap((classInfo) => [
    ...(classInfo.coverage === "documented"
      ? [{
          label: "Class",
          name: classInfo.class,
          file: classInfo.source_file,
          documentationFile: classInfo.documentation_file,
        }]
      : []),
    ...classInfo.methods
      .filter((method) => method.coverage === "documented")
      .map((method) => ({
        label: "Method",
        name: `${classInfo.class}.${method.signature}`,
        file: classInfo.source_file,
        documentationFile: method.documentation_file,
      })),
  ]);

  return (
    <div className="grid gap-5 xl:grid-cols-3">
      <StatusList
        title="Documented"
        description="Elements the backend mapped to documentation."
        status="Documented"
        items={documentedElements}
        available={available}
      />
      <StatusList
        title="Ambiguous mappings"
        description="Backend results that do not identify a unique mapping."
        status="Ambiguous mapping"
        items={ambiguousFindings.length > 0 ? [] : ambiguousElements}
        findings={ambiguousFindings}
        available={available}
      />
      <StatusList
        title="Unsupported mappings"
        description="Elements whose coverage could not be determined."
        status="Unsupported mapping"
        items={unsupportedFindings.length > 0 ? [] : unsupportedElements}
        findings={unsupportedFindings}
        available={available}
      />
    </div>
  );
}

function StatusList({
  title,
  description,
  status,
  items,
  findings = [],
  available = true,
}: {
  title: string;
  description: string;
  status: string;
  items: Array<{
    label: string;
    name: string;
    file: string;
    documentationFile?: string | null;
  }>;
  findings?: DocumentationFinding[];
  available?: boolean;
}) {
  const emptyMessage: Record<string, string> = {
    Documented: "No documented elements reported.",
    "Ambiguous mapping": "No ambiguous mappings reported.",
    "Unsupported mapping": "No unsupported mappings reported.",
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          {items.length || findings.length}
        </span>
      </div>
      <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
      {items.length === 0 && findings.length === 0 ? (
        <p className="mt-4 text-xs text-slate-500">
          {available
            ? emptyMessage[status] ?? "No mapping results reported."
            : `${title} details were not included in the response.`}
        </p>
      ) : (
        <ul className="mt-3 max-h-80 space-y-2 overflow-y-auto">
          {items.map((item, index) => (
            <li
              key={`${item.file}-${item.name}-${index}`}
              className="rounded-lg bg-slate-50 px-3 py-2"
            >
              <span className="rounded bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                {status}
              </span>
              <p className="mt-1 break-all text-xs font-medium text-slate-800">
                {item.label}: {item.name}
              </p>
              <p className="mt-1 break-all font-mono text-[11px] text-slate-500">
                {item.file}
              </p>
              {item.documentationFile && (
                <p className="mt-1 break-all text-[11px] text-slate-600">
                  Documentation: {item.documentationFile}
                </p>
              )}
            </li>
          ))}
          {findings.map((finding, index) => (
            <li
              key={`${finding.class}-${finding.method}-${index}`}
              className="rounded-lg bg-slate-50 px-3 py-2"
            >
              <span className="rounded bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                {status}
              </span>
              <p className="mt-1 text-xs font-medium text-slate-800">
                {finding.class ?? "Class not provided"}
                {finding.method ? ` · ${finding.method}` : ""}
              </p>
              {finding.reason && (
                <p className="mt-1 text-xs leading-5 text-slate-600">
                  {finding.reason}
                </p>
              )}
              {evidenceList(finding, "documentation_files").length > 0 && (
                <p className="mt-1 break-all text-[11px] text-slate-600">
                  Candidate documentation:{" "}
                  {evidenceList(finding, "documentation_files").join(", ")}
                </p>
              )}
              {evidenceList(finding, "matching_headings").length > 0 && (
                <p className="mt-1 break-all text-[11px] text-slate-600">
                  Matching headings:{" "}
                  {evidenceList(finding, "matching_headings").join(", ")}
                </p>
              )}
              {finding.source_file && (
                <p className="mt-1 break-all font-mono text-[11px] text-slate-500">
                  {finding.source_file}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
