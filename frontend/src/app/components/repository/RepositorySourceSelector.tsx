"use client";

import { useState } from "react";
import { Loader2, Plus } from "lucide-react";
import { isValidGithubRepositoryUrl, validateZipFile } from "@/lib/repositoryImportValidation";

type Source = "github" | "local" | "zip";

interface Props {
  hosted: boolean;
  repositoryPath: string;
  onPathChange: (value: string) => void;
  onAddLocal: () => void;
  adding: boolean;
}

export default function RepositorySourceSelector({
  hosted, repositoryPath, onPathChange, onAddLocal, adding,
}: Props) {
  const [source, setSource] = useState<Source>(hosted ? "github" : "local");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const githubError = url && !isValidGithubRepositoryUrl(url)
    ? "Enter a public GitHub HTTPS repository URL, such as https://github.com/owner/repository."
    : "";
  const zipError = file ? validateZipFile(file) : null;
  const sources: { id: Source; label: string }[] = [
    { id: "github", label: "GitHub Repository URL" },
    ...(!hosted ? [{ id: "local" as const, label: "Local Repository Path" }] : []),
    ...(hosted ? [{ id: "zip" as const, label: "ZIP Upload" }] : []),
  ];

  return (
    <section className="mb-8 rounded-xl border border-white/10 bg-[#111a2e] p-6">
      <div className="mb-5 flex items-center gap-3">
        <div className="rounded-lg bg-blue-500/10 p-2.5 text-blue-400"><Plus size={20} /></div>
        <div>
          <h2 className="font-semibold">Add a repository</h2>
          <p className="mt-1 text-xs text-slate-400">Choose how to provide your repository.</p>
        </div>
      </div>
      <fieldset disabled={adding}>
        <legend className="mb-3 text-sm font-medium text-slate-300">Repository source</legend>
        <div className="mb-5 flex flex-wrap gap-3">
          {sources.map((option) => (
            <label key={option.id} className="flex cursor-pointer items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-200 has-[:checked]:border-blue-400 has-[:checked]:bg-blue-500/10">
              <input type="radio" name="repository-source" value={option.id}
                checked={source === option.id} onChange={() => setSource(option.id)}
                className="accent-blue-500" />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      {source === "local" && !hosted && (
        <form onSubmit={(event) => { event.preventDefault(); onAddLocal(); }} noValidate>
          <label htmlFor="repositoryPath" className="mb-2 block text-sm text-slate-300">Repository path</label>
          <p id="local-path-help" className="mb-3 text-xs text-slate-400">
            Enter an absolute path accessible to the trusted local backend, not a path on a remote browser.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input id="repositoryPath" value={repositoryPath} onChange={(event) => onPathChange(event.target.value)}
              placeholder={String.raw`D:\projects\my-repository`} autoComplete="off" disabled={adding}
              aria-describedby="local-path-help"
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-[#0b1020] px-4 py-3 text-sm outline-none focus:border-blue-500" />
            <button type="submit" disabled={adding}
              className="flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60">
              {adding ? <><Loader2 size={17} className="animate-spin" />Registering...</> : <><Plus size={17} />Add Repository</>}
            </button>
          </div>
        </form>
      )}

      {source === "github" && (
        <div>
          <label htmlFor="github-url" className="mb-2 block text-sm text-slate-300">GitHub repository URL</label>
          <input id="github-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)}
            placeholder="https://github.com/owner/repository" autoComplete="url" spellCheck={false}
            aria-invalid={Boolean(githubError)} aria-describedby="github-help github-validation"
            className="w-full rounded-lg border border-white/10 bg-[#0b1020] px-4 py-3 text-sm outline-none focus:border-blue-500" />
          <p id="github-help" className="mt-2 text-xs text-slate-400">
            Public GitHub HTTPS URLs only. Availability cannot be checked until import is enabled.
          </p>
          <p id="github-validation" aria-live="polite" className={`mt-2 text-xs ${githubError ? "text-red-300" : "text-emerald-300"}`}>
            {githubError || (url ? "URL format is valid." : "")}
          </p>
          <button type="button" disabled aria-describedby="imports-unavailable"
            className="mt-4 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold opacity-50">
            Import from GitHub
          </button>
        </div>
      )}

      {source === "zip" && hosted && (
        <div>
          <label htmlFor="repository-zip" className="mb-2 block text-sm text-slate-300">Repository ZIP file</label>
          <input id="repository-zip" type="file" accept=".zip,application/zip"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            aria-invalid={Boolean(zipError)} aria-describedby="zip-help zip-validation"
            className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-blue-600 file:px-4 file:py-2 file:text-white" />
          <p id="zip-help" className="mt-2 text-xs text-slate-400">
            ZIP files up to 25 MiB; this preliminary limit may change when secure uploads are available. ZIP imports do not preserve Git history.
          </p>
          {file && <p className="mt-2 break-all text-xs text-slate-300">{file.name} ({(file.size / (1024 * 1024)).toFixed(2)} MiB)</p>}
          <p id="zip-validation" aria-live="polite" className={`mt-2 break-all text-xs ${zipError ? "text-red-300" : "text-emerald-300"}`}>
            {file && (zipError || "ZIP file selected.")}
          </p>
          <button type="button" disabled aria-describedby="imports-unavailable"
            className="mt-4 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold opacity-50">
            Upload ZIP
          </button>
        </div>
      )}
      {source !== "local" && (
        <p id="imports-unavailable" className="mt-3 text-xs text-amber-300">
          {hosted ? "Hosted repository imports are not yet available." : "GitHub imports are not yet available."} Secure import endpoints and verified workspace quotas are required.
        </p>
      )}
    </section>
  );
}
