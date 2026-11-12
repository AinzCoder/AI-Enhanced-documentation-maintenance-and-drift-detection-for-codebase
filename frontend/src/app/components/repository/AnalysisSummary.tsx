import { BookOpenCheck, Boxes, Braces, FileCode2, FileText } from "lucide-react";
import type {
  AnalysisMode,
  AnalyzeResponse,
  FullAnalyzeResponse,
} from "@/types/api";

interface AnalysisSummaryProps {
  mode: AnalysisMode;
  repository: string;
  full?: FullAnalyzeResponse;
  git?: AnalyzeResponse;
}

function Metric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: typeof FileCode2;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-slate-600">{label}</p>
        <Icon aria-hidden="true" size={16} className="text-slate-400" />
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums text-slate-900">
        {value}
      </p>
    </article>
  );
}

export default function AnalysisSummary({
  mode,
  repository,
  full,
  git,
}: AnalysisSummaryProps) {
  const metrics = full
    ? [
        {
          label: "Java files analyzed",
          value: full.summary.files_analyzed,
          icon: FileCode2,
        },
        {
          label: "Classes detected",
          value: full.summary.class_count,
          icon: Boxes,
        },
        {
          label: "Methods detected",
          value: full.summary.method_count,
          icon: Braces,
        },
        {
          label: "Documentation files",
          value: full.documentation_files.length,
          icon: FileText,
        },
      ]
    : git
      ? [
          {
            label: "Changed Java files",
            value: git.results.length,
            icon: FileCode2,
          },
          {
            label: "Detected changes",
            value: git.results.reduce(
              (total, result) => total + result.changes.length,
              0
            ),
            icon: Braces,
          },
          {
            label: "Files with errors",
            value: git.results.filter((result) => (result.errors?.length ?? 0) > 0)
              .length,
            icon: FileText,
          },
        ]
      : [];

  return (
    <section aria-labelledby="analysis-summary-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-cyan-700">
            {mode === "full" ? "Full repository analysis" : "Git change analysis"}
          </p>
          <h2
            id="analysis-summary-heading"
            className="mt-1 break-all text-xl font-semibold text-slate-950"
          >
            {repository}
          </h2>
        </div>
        {full && full.summary.files_with_errors > 0 && (
          <span className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">
            Partial analysis · {full.summary.files_with_errors} file errors
          </span>
        )}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metrics.map((metric) => (
          <Metric key={metric.label} {...metric} />
        ))}
      </div>

      {full?.documentation_analysis && (
        <section
          aria-labelledby="documentation-coverage-heading"
          className="mt-4 rounded-xl border border-cyan-100 bg-cyan-50/60 p-4"
        >
          <div className="flex items-center gap-2">
            <BookOpenCheck aria-hidden="true" size={17} className="text-cyan-800" />
            <h3
              id="documentation-coverage-heading"
              className="text-sm font-semibold text-slate-900"
            >
              Documentation coverage
            </h3>
          </div>
          <div className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <p>
              Classes documented:{" "}
              <strong>
                {full.documentation_analysis.summary.documented_class_count}
              </strong>
            </p>
            <p>
              Classes missing docs:{" "}
              <strong>
                {full.documentation_analysis.summary.missing_class_count}
              </strong>
            </p>
            <p>
              Methods documented:{" "}
              <strong>
                {full.documentation_analysis.summary.documented_method_count}
              </strong>
            </p>
            <p>
              Methods missing docs:{" "}
              <strong>
                {full.documentation_analysis.summary.missing_method_count}
              </strong>
            </p>
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-600">
            Coverage and mapping findings are reported by the backend. For
            change-linked drift, open Documentation Drift and run a working-tree
            comparison.
          </p>
        </section>
      )}
      {git && (
        <p className="mt-3 text-xs text-slate-500">
          Compared commits: {git.previous_commit ?? "Not available"} →{" "}
          {git.current_commit ?? "Not available"}
        </p>
      )}
    </section>
  );
}
