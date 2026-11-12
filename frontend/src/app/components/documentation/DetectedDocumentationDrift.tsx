"use client";

import { AlertTriangle, GitBranch } from "lucide-react";
import { useState } from "react";
import type { AnalyzeResponse, DriftFinding } from "@/types/api";

const PAGE_SIZE = 20;

function evidenceFiles(finding: DriftFinding): string[] {
  const evidence = finding.evidence;
  if (!evidence || typeof evidence !== "object") {
    return [];
  }
  const files = evidence.documentation_files;
  return Array.isArray(files)
    ? files.filter((file): file is string => typeof file === "string")
    : [];
}

function evidenceHeadings(finding: DriftFinding): string[] {
  const evidence = finding.evidence;
  if (!evidence || typeof evidence !== "object") {
    return [];
  }
  const headings = evidence.matching_headings;
  return Array.isArray(headings)
    ? headings.filter(
        (heading): heading is string => typeof heading === "string"
      )
    : [];
}

export default function DetectedDocumentationDrift({
  result,
}: {
  result: AnalyzeResponse;
}) {
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const filesWithDrift = result.results.filter((file) => file.drift.length > 0);
  const findings = filesWithDrift.flatMap((file) =>
    file.drift.map((finding) => ({ file: file.file, finding }))
  );

  return (
    <section
      aria-labelledby="detected-drift-heading"
      className="rounded-2xl border border-violet-200 bg-white p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <GitBranch
              aria-hidden="true"
              size={18}
              className="text-violet-700"
            />
            <h2
              id="detected-drift-heading"
              className="text-lg font-semibold text-slate-950"
            >
              Detected documentation drift
            </h2>
          </div>
          <p className="mt-1 text-sm leading-5 text-slate-600">
            Backend findings linked to Java changes in the working tree.
          </p>
        </div>
        <span className="rounded-full bg-violet-50 px-3 py-1 text-xs font-medium text-violet-900">
          {findings.length} finding{findings.length === 1 ? "" : "s"}
        </span>
      </div>

      {findings.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-700">
          {result.results.length === 0
            ? "No Java changes were returned for the working tree."
            : "No documentation drift findings were returned for the changed Java files."}
        </div>
      ) : (
        <ul className="mt-4 space-y-3">
          {findings.slice(0, visibleCount).map(({ file, finding }, index) => {
            const files = evidenceFiles(finding);
            const headings = evidenceHeadings(finding);
            return (
              <li
                key={`${file}-${finding.finding_type ?? finding.type}-${index}`}
                className="rounded-xl border border-violet-100 bg-violet-50/40 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-900">
                    {finding.finding_type ?? finding.type ?? "Backend finding"}
                  </span>
                  {finding.change_type && (
                    <span className="rounded bg-white px-2 py-1 font-mono text-[11px] text-slate-700">
                      {finding.change_type}
                    </span>
                  )}
                  {finding.review_classification && (
                    <span className="text-xs text-slate-500">
                      {finding.review_classification}
                    </span>
                  )}
                </div>
                <p className="mt-2 break-all font-mono text-xs text-slate-600">
                  {finding.source_file ?? file}
                </p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {finding.class ?? "Class not provided"}
                  {finding.method ? ` · ${finding.method}` : ""}
                </p>
                {finding.reason && (
                  <p className="mt-2 text-sm leading-6 text-slate-700">
                    {finding.reason}
                  </p>
                )}
                {finding.documentation_target && (
                  <p className="mt-2 break-all text-xs text-slate-600">
                    Documentation target:{" "}
                    <span className="font-mono">
                      {finding.documentation_target}
                    </span>
                  </p>
                )}
                {files.length > 0 && (
                  <p className="mt-2 break-all text-xs text-slate-600">
                    Candidate documentation: {files.join(", ")}
                  </p>
                )}
                {headings.length > 0 && (
                  <p className="mt-2 text-xs text-slate-600">
                    Matching headings: {headings.join(", ")}
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {findings.length > visibleCount && (
        <button
          type="button"
          onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
          className="mt-4 min-h-10 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600"
        >
          Show more ({findings.length - visibleCount} remaining)
        </button>
      )}
      <p className="mt-4 flex items-start gap-2 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">
        <AlertTriangle
          aria-hidden="true"
          size={15}
          className="mt-0.5 shrink-0"
        />
        Findings are returned by the backend comparison. They are review
        signals, not automatic documentation edits.
      </p>
    </section>
  );
}
