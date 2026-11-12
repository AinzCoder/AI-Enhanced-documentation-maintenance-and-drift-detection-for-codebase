import type { AnalysisError } from "@/types/api";

interface AnalysisErrorPanelProps {
  title?: string;
  message?: string;
  errors?: AnalysisError[];
}

export default function AnalysisErrorPanel({
  title = "Analysis needs attention",
  message,
  errors = [],
}: AnalysisErrorPanelProps) {
  if (!message && errors.length === 0) {
    return null;
  }

  return (
    <section
      aria-labelledby="analysis-errors-title"
      className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-950"
      role="alert"
    >
      <h2 id="analysis-errors-title" className="text-sm font-semibold">
        {title}
      </h2>
      {message && <p className="mt-1 text-sm leading-6">{message}</p>}
      {errors.length > 0 && (
        <ul className="mt-3 space-y-2 text-sm">
          {errors.map((error, index) => (
            <li
              key={`${error.stage}-${error.file ?? "repository"}-${index}`}
              className="rounded-lg border border-rose-200/80 bg-white/70 px-3 py-2"
            >
              <span className="font-medium">{error.stage}</span>
              {error.file && <span> · {error.file}</span>}
              <p className="mt-1 break-words leading-5">{error.message}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
