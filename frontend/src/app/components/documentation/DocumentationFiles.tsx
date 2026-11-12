import { FileText, Target } from "lucide-react";
import type { DocumentationFinding } from "@/types/api";

export default function DocumentationFiles({
  files,
  emptyFindings,
  errors,
  targets,
  filesAvailable = true,
  targetsAvailable = true,
  emptyFindingsAvailable = true,
}: {
  files: string[];
  emptyFindings: DocumentationFinding[];
  errors: Array<{ file?: string | null; stage: string; message: string }>;
  targets: string[];
  filesAvailable?: boolean;
  targetsAvailable?: boolean;
  emptyFindingsAvailable?: boolean;
}) {
  const emptyFiles = new Set(
    emptyFindings
      .map(
        (finding) =>
          finding.documentation_file ?? finding.documentation_target
      )
      .filter((path): path is string => typeof path === "string")
  );
  const unreadableFiles = new Set(
    errors
      .map((error) => error.file)
      .filter((path): path is string => typeof path === "string")
  );

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section
        aria-labelledby="documentation-files-heading"
        className="rounded-xl border border-slate-200 bg-white p-4"
      >
        <div className="flex items-center gap-2">
          <FileText aria-hidden="true" size={17} className="text-cyan-700" />
          <h2
            id="documentation-files-heading"
            className="text-sm font-semibold text-slate-900"
          >
            Documentation files
          </h2>
        </div>
        {!filesAvailable ? (
          <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            The response did not include a documentation file list.
          </p>
        ) : files.length === 0 ? (
          <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            No documentation files were discovered by the backend.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {files.map((file) => {
              const status = unreadableFiles.has(file)
                ? "Unreadable"
                : emptyFiles.has(file)
                  ? "Empty"
                  : emptyFindingsAvailable
                    ? "Nonempty"
                    : "Status unavailable";
              const style =
                status === "Unreadable"
                  ? "bg-rose-50 text-rose-800"
                  : status === "Empty"
                    ? "bg-amber-50 text-amber-800"
                    : status === "Nonempty"
                      ? "bg-emerald-50 text-emerald-800"
                      : "bg-slate-100 text-slate-700";
              return (
                <li
                  key={file}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2"
                >
                  <span className="break-all font-mono text-xs text-slate-800">
                    {file}
                  </span>
                  <span
                    className={`rounded-full px-2 py-1 text-[11px] font-medium ${style}`}
                  >
                    {status}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      <section
        aria-labelledby="documentation-targets-heading"
        className="rounded-xl border border-slate-200 bg-white p-4"
      >
        <div className="flex items-center gap-2">
          <Target aria-hidden="true" size={17} className="text-cyan-700" />
          <h2
            id="documentation-targets-heading"
            className="text-sm font-semibold text-slate-900"
          >
            Proposed documentation targets
          </h2>
        </div>
        {!targetsAvailable ? (
          <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            Proposed targets were not included in the response.
          </p>
        ) : targets.length === 0 ? (
          <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            No target recommendations were returned.
          </p>
        ) : (
          <>
            <p className="mt-2 text-xs text-slate-500">
              Recommendations only. These paths are not confirmed as existing
              files and no files have been changed.
            </p>
            <ul className="mt-3 space-y-2">
              {targets.map((target) => (
                <li
                  key={target}
                  className="break-all rounded-lg bg-cyan-50 px-3 py-2 font-mono text-xs text-cyan-950"
                >
                  {target}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}
