import {
  BookOpenCheck,
  Boxes,
  Braces,
  FileCode2,
  FileText,
} from "lucide-react";
import type { CoverageSummary } from "@/types/api";

type Summary = Partial<CoverageSummary>;

function percentage(documented: number | undefined, total: number | undefined) {
  if (
    typeof documented !== "number" ||
    typeof total !== "number" ||
    total === 0
  ) {
    return "N/A";
  }
  return `${Math.round((documented / total) * 100)}%`;
}

function Metric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number | undefined;
  icon: typeof FileCode2;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-slate-600">{label}</p>
        <Icon aria-hidden="true" size={16} className="text-slate-400" />
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums text-slate-900">
        {value ?? "Not available"}
      </p>
    </article>
  );
}

export default function DocumentationCoverageSummary({
  summary,
}: {
  summary: Summary;
}) {
  const metrics = [
    { label: "Java files", value: summary.java_file_count, icon: FileCode2 },
    { label: "Classes", value: summary.class_count, icon: Boxes },
    { label: "Methods", value: summary.method_count, icon: Braces },
    {
      label: "Documented classes",
      value: summary.documented_class_count,
      icon: BookOpenCheck,
    },
    {
      label: "Missing class documentation",
      value: summary.missing_class_count,
      icon: Boxes,
    },
    {
      label: "Documented methods",
      value: summary.documented_method_count,
      icon: BookOpenCheck,
    },
    {
      label: "Missing method documentation",
      value: summary.missing_method_count,
      icon: Braces,
    },
    {
      label: "Ambiguous class mappings",
      value: summary.ambiguous_class_count,
      icon: FileText,
    },
    {
      label: "Unsupported class mappings",
      value: summary.unsupported_class_count,
      icon: FileText,
    },
    {
      label: "Ambiguous method mappings",
      value: summary.ambiguous_method_count,
      icon: FileText,
    },
    {
      label: "Unsupported method mappings",
      value: summary.unsupported_method_count,
      icon: FileText,
    },
    {
      label: "Documentation files",
      value: summary.documentation_file_count,
      icon: FileText,
    },
    {
      label: "Empty documentation files",
      value: summary.empty_documentation_file_count,
      icon: FileText,
    },
  ];

  return (
    <section aria-labelledby="coverage-summary-heading">
      <div className="mb-4">
        <h2
          id="coverage-summary-heading"
          className="text-xl font-semibold text-slate-950"
        >
          Documentation Coverage
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          Counts reflect the backend coverage analysis. Ambiguous and
          unsupported items are reported separately from missing documentation.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {metrics.map((metric) => (
          <Metric key={metric.label} {...metric} />
        ))}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <CoverageProgress
          label="Class coverage"
          documented={summary.documented_class_count}
          total={summary.class_count}
        />
        <CoverageProgress
          label="Method coverage"
          documented={summary.documented_method_count}
          total={summary.method_count}
        />
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">
        Coverage is documented elements divided by all analyzed classes or
        methods. Ambiguous and unsupported elements remain in the denominator,
        so percentages represent confirmed coverage, not overall documentation
        quality.
      </p>
    </section>
  );
}

function CoverageProgress({
  label,
  documented,
  total,
}: {
  label: string;
  documented: number | undefined;
  total: number | undefined;
}) {
  const percentageLabel = percentage(documented, total);
  const numericPercentage =
    percentageLabel === "N/A"
      ? undefined
      : Number.parseInt(percentageLabel, 10);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-slate-800">{label}</h3>
        <span className="text-sm font-semibold tabular-nums text-slate-900">
          {percentageLabel}
        </span>
      </div>
      <div
        className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
        aria-label={label}
        aria-valuemin={numericPercentage === undefined ? undefined : 0}
        aria-valuemax={numericPercentage === undefined ? undefined : 100}
        aria-valuenow={numericPercentage}
        aria-valuetext={
          numericPercentage === undefined
            ? "Not available"
            : `${percentageLabel} documented`
        }
      >
        {numericPercentage !== undefined && (
          <div
            className="h-full rounded-full bg-cyan-600"
            style={{ width: `${numericPercentage}%` }}
          />
        )}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {documented ?? "Not available"} documented / {total ?? "Not available"}{" "}
        total
      </p>
    </div>
  );
}
