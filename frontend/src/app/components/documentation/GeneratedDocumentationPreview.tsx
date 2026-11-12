"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

export default function GeneratedDocumentationPreview({
  markdown,
  partial,
}: {
  markdown: string;
  partial: boolean;
}) {
  const [rawView, setRawView] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");

  async function copyMarkdown() {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopyMessage("Markdown copied to clipboard.");
    } catch {
      setCopyMessage("Clipboard access failed. Select and copy the Markdown manually.");
    }
  }

  return (
    <section
      aria-labelledby="generated-preview-heading"
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2
            id="generated-preview-heading"
            className="text-lg font-semibold text-slate-950"
          >
            Generated Markdown preview
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            {markdown.length.toLocaleString()} characters. This preview is plain
            text; generated Markdown is never rendered as HTML.
          </p>
        </div>
        <button
          type="button"
          onClick={copyMarkdown}
          className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-slate-300 px-3 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2"
        >
          {copyMessage === "Markdown copied to clipboard." ? (
            <Check aria-hidden="true" size={16} />
          ) : (
            <Copy aria-hidden="true" size={16} />
          )}
          Copy Markdown
        </button>
      </div>

      {partial && (
        <div
          role="status"
          className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-900"
        >
          This is a partial result. Review the backend-reported warnings and
          errors before using the preview.
        </div>
      )}

      <p className="mt-4 rounded-lg border border-cyan-100 bg-cyan-50 px-4 py-3 text-sm leading-6 text-cyan-950">
        Generated documentation is a preview. Repository documentation is not
        updated until a developer explicitly approves the change.
      </p>

      <div className="mt-4 flex flex-wrap gap-2" aria-label="Preview format">
        <button
          type="button"
          aria-pressed={!rawView}
          onClick={() => setRawView(false)}
          className="min-h-9 rounded-lg px-3 text-sm font-medium text-slate-700 outline-none hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-cyan-600 aria-pressed:bg-slate-900 aria-pressed:text-white"
        >
          Readable text
        </button>
        <button
          type="button"
          aria-pressed={rawView}
          onClick={() => setRawView(true)}
          className="min-h-9 rounded-lg px-3 text-sm font-medium text-slate-700 outline-none hover:bg-slate-100 focus-visible:ring-2 focus-visible:ring-cyan-600 aria-pressed:bg-slate-900 aria-pressed:text-white"
        >
          Raw Markdown
        </button>
      </div>

      {rawView ? (
        <textarea
          aria-label="Raw generated Markdown"
          readOnly
          value={markdown}
          rows={18}
          className="mt-3 w-full resize-y rounded-xl border border-slate-200 bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-100 outline-none focus-visible:ring-2 focus-visible:ring-cyan-600"
        />
      ) : (
        <pre className="mt-3 max-h-[42rem] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-slate-50 p-4 font-sans text-sm leading-7 text-slate-800">
          {markdown}
        </pre>
      )}

      <p aria-live="polite" className="mt-2 min-h-5 text-xs text-slate-600">
        {copyMessage}
      </p>
    </section>
  );
}
