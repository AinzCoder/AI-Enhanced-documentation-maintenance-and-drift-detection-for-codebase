import { FileDiff } from "lucide-react";
import type { AnalyzeFileResult, CodeChange } from "@/types/api";

function displayValue(value: unknown): string | null {
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  return null;
}

function ChangeDetails({ change }: { change: CodeChange }) {
  const visibleFields = [
    ["Class", change.class],
    ["Method", change.method],
    ["Signature", change.method_signature],
    ["Parameter", change.parameter],
    ["Old parameter", change.old_parameter],
    ["New parameter", change.new_parameter],
    ["Parameter type", change.parameter_type],
    ["Old parameter type", change.old_parameter_type],
    ["New parameter type", change.new_parameter_type],
    ["Reason", change.reason],
    ["Old return type", change.old_return_type],
    ["New return type", change.new_return_type],
  ]
    .map(([label, value]) => [label, displayValue(value)] as const)
    .filter((entry): entry is readonly [string, string] => entry[1] !== null);

  return (
    <li className="rounded-lg border border-slate-200 bg-white px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-violet-50 px-2 py-1 font-mono text-xs font-semibold text-violet-800">
          {change.type ?? "Change type unavailable"}
        </span>
        {(typeof change.start_line === "number" ||
          typeof change.old_start_line === "number") && (
          <span className="text-xs text-slate-500">
            {typeof change.start_line === "number"
              ? `Line ${change.start_line}`
              : `Old line ${change.old_start_line}`}
          </span>
        )}
      </div>
      {visibleFields.length > 0 && (
        <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
          {visibleFields.map(([label, value]) => (
            <div key={label} className="flex gap-1">
              <dt className="shrink-0 text-slate-500">{label}:</dt>
              <dd className="break-all text-slate-800">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </li>
  );
}

export default function GitChangeList({
  results,
}: {
  results: AnalyzeFileResult[];
}) {
  if (results.length === 0) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 text-center">
        <FileDiff aria-hidden="true" className="mx-auto text-slate-400" size={22} />
        <h2 className="mt-2 text-sm font-semibold text-slate-800">
          No Java changes were returned.
        </h2>
        <p className="mt-1 text-xs text-slate-500">
          The selected Git comparison completed and found no Java file changes.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="git-changes-heading">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2
          id="git-changes-heading"
          className="text-base font-semibold text-slate-900"
        >
          Changed Java files
        </h2>
        <span className="text-xs text-slate-500">{results.length} files</span>
      </div>
      <div className="space-y-3">
        {results.map((result, index) => (
          <article
            key={`${result.file}-${index}`}
            className="rounded-xl border border-slate-200 bg-white p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="break-all font-mono text-sm font-medium text-slate-900">
                {result.file}
              </h3>
              <div className="flex shrink-0 gap-2">
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                  {result.change_type}
                </span>
                {result.git_change_type !== result.change_type && (
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                    Git {result.git_change_type}
                  </span>
                )}
              </div>
            </div>
            {result.changes.length > 0 ? (
              <ul className="mt-3 space-y-2">
                {result.changes.map((change, changeIndex) => (
                  <ChangeDetails
                    key={`${change.type ?? "change"}-${changeIndex}`}
                    change={change}
                  />
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-xs text-slate-500">
                No class or method changes were identified for this file.
              </p>
            )}
            {result.drift.length > 0 && (
              <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
                Backend-reported documentation findings: {result.drift.length}
                <ul className="mt-1 list-inside list-disc">
                  {result.drift.map((finding, findingIndex) => (
                    <li key={`${finding.type ?? "finding"}-${findingIndex}`}>
                      {finding.type ?? finding.finding_type ?? "Finding"}
                      {finding.reason ? ` — ${finding.reason}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {result.documentation_files.length > 0 && (
              <p className="mt-3 text-xs text-slate-500">
                Mapped documentation: {result.documentation_files.join(", ")}
              </p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
