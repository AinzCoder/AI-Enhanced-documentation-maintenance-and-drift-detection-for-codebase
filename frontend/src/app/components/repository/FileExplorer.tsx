"use client";

import { ChevronDown, ChevronRight, FileCode2 } from "lucide-react";
import { useState } from "react";
import type { AnalysisError, FullAnalysisFile } from "@/types/api";

export default function FileExplorer({
  files,
  errors = [],
}: {
  files: FullAnalysisFile[];
  errors?: AnalysisError[];
}) {
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());

  if (files.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
        <p className="text-sm font-medium text-slate-700">
          No Java files were found.
        </p>
        <p className="mt-1 text-xs text-slate-500">
          The repository scan completed without Java source files.
        </p>
      </div>
    );
  }

  function toggleFile(filePath: string) {
    setExpandedFiles((current) => {
      const next = new Set(current);
      if (next.has(filePath)) {
        next.delete(filePath);
      } else {
        next.add(filePath);
      }
      return next;
    });
  }

  return (
    <section aria-labelledby="source-files-heading">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2
          id="source-files-heading"
          className="text-base font-semibold text-slate-900"
        >
          Java source files
        </h2>
        <span className="text-xs text-slate-500">{files.length} files</span>
      </div>
      <div className="space-y-2">
        {files.map((file, index) => {
          const expanded = expandedFiles.has(file.file);
          const fileErrors = errors.filter((error) => error.file === file.file);
          const buttonId = `source-file-${index}`;
          const panelId = `source-file-details-${index}`;
          return (
            <article
              key={`${file.file}-${index}`}
              className="overflow-hidden rounded-xl border border-slate-200 bg-white"
            >
              <h3>
                <button
                  id={buttonId}
                  type="button"
                  aria-expanded={expanded}
                  aria-controls={panelId}
                  onClick={() => toggleFile(file.file)}
                  className="flex min-h-14 w-full items-center gap-3 px-4 py-3 text-left outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-cyan-600"
                >
                  {expanded ? (
                    <ChevronDown
                      aria-hidden="true"
                      size={17}
                      className="shrink-0 text-slate-500"
                    />
                  ) : (
                    <ChevronRight
                      aria-hidden="true"
                      size={17}
                      className="shrink-0 text-slate-500"
                    />
                  )}
                  <FileCode2
                    aria-hidden="true"
                    size={17}
                    className="shrink-0 text-cyan-700"
                  />
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-800 sm:text-sm">
                    {file.file}
                  </span>
                  <span className="shrink-0 text-xs text-slate-500">
                    {file.class_count} classes · {file.method_count} methods
                    {fileErrors.length > 0 &&
                      ` · ${fileErrors.length} errors`}
                  </span>
                </button>
              </h3>
              {expanded && (
                <div
                  id={panelId}
                  role="region"
                  aria-labelledby={buttonId}
                  className="border-t border-slate-100 px-4 py-4 sm:px-6"
                >
                  <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
                    <span>Language: Java</span>
                    <span>Package: {file.package ?? "Not available"}</span>
                    <span>
                      Lines: {file.line_count ?? "Not available"}
                    </span>
                  </div>
                  {fileErrors.length > 0 && (
                    <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900">
                      <p className="font-semibold">File analysis errors</p>
                      <ul className="mt-2 space-y-1">
                        {fileErrors.map((error, errorIndex) => (
                          <li key={`${error.stage}-${errorIndex}`}>
                            <span className="font-medium">{error.stage}:</span>{" "}
                            {error.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {file.classes.length === 0 ? (
                    <p className="text-sm text-slate-500">
                      No classes were extracted from this file.
                    </p>
                  ) : (
                    <div className="space-y-4">
                      {file.classes.map((classInfo, classIndex) => (
                        <section
                          key={`${classInfo.name}-${classIndex}`}
                          className="rounded-lg bg-slate-50 p-4"
                        >
                          <h4 className="font-mono text-sm font-semibold text-slate-900">
                            {classInfo.name}
                          </h4>
                          {classInfo.comment && (
                            <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                              {classInfo.comment}
                            </p>
                          )}
                          {classInfo.methods.length === 0 ? (
                            <p className="mt-3 text-xs text-slate-500">
                              No methods detected.
                            </p>
                          ) : (
                            <ul className="mt-3 space-y-2">
                              {classInfo.methods.map((method, methodIndex) => (
                                <li
                                  key={`${method.signature}-${methodIndex}`}
                                  className="rounded-md border border-slate-200 bg-white px-3 py-2"
                                >
                                  <code className="break-all text-xs font-semibold text-slate-800">
                                    {method.signature}
                                  </code>
                                  <p className="mt-1 text-xs text-slate-500">
                                    Returns: {method.return_type ?? "Not available"}
                                    {method.parameters.length > 0 && (
                                      <>
                                        {" · Parameters: "}
                                        {method.parameters
                                          .map(
                                            (parameter) =>
                                              `${parameter.type ?? "?"} ${parameter.name}`
                                          )
                                          .join(", ")}
                                      </>
                                    )}
                                  </p>
                                </li>
                              ))}
                            </ul>
                          )}
                        </section>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
