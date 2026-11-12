
"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { apiBaseUrl } from "@/lib/apiBaseUrl";
import {
  Sparkles,
  FileText,
  CheckCircle,
  XCircle,
  Save,
  Loader2,
} from "lucide-react";

type SuggestionResult = {
  class: string;
  method: string;
  change_type: string;
  target_documentation: string;
  retrieved_documents: {
    chunk: number;
    file: string;
    type: string;
  }[];
  suggestion: string;
  developer_comment: string | null;
  error?: string;
};

export default function SuggestionsPage() {
  const [repositoryPath, setRepositoryPath] = useState("");

  const [filePath, setFilePath] = useState("");
  const [className, setClassName] = useState("");
  const [methodName, setMethodName] = useState("");
  const [changeType, setChangeType] = useState("");

  const [result, setResult] = useState<SuggestionResult | null>(null);
  const [documentation, setDocumentation] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  // Read the selected change from the Dashboard URL.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(window.location.search);

      const repository = params.get("repository");
      const file = params.get("file");
      const classValue = params.get("class");
      const method = params.get("method");
      const change = params.get("changeType");

      if (repository) setRepositoryPath(repository);
      if (file) setFilePath(file);
      if (classValue) setClassName(classValue);
      if (method) setMethodName(method);
      if (change) setChangeType(change);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);


  const generateSuggestion = async () => {
    if (
      !repositoryPath.trim() ||
      !filePath.trim() ||
      !className.trim() ||
      !methodName.trim() ||
      !changeType
    ) {
      setError("No valid code change selected. Run repository analysis and select a detected change first.");
      return;
    }
    setLoading(true);
    setError("");
    setMessage("");
    setResult(null);

    try {
      const response = await axios.post<SuggestionResult>(
        `${apiBaseUrl}/suggest`,
        {
          repository_path: repositoryPath,
          file_path: filePath,
          class_name: className,
          method_name: methodName,
          change_type: changeType,
        }
      );

      if (response.data.error) {
        setError(response.data.error);
        return;
      }

      setResult(response.data);
      setDocumentation(response.data.suggestion);
    } catch (err) {
      console.error(err);
      setError("Could not generate the suggestion. Check FastAPI and Groq.");
    } finally {
      setLoading(false);
    }
  };

  const submitDecision = async (decision: "approve" | "reject" | "edit") => {
    if (!result) return;

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const response = await axios.post(`${apiBaseUrl}/decision`, {
        repository_path: repositoryPath,
        documentation_file: result.target_documentation,
        class_name: result.class,
        method_name: result.method,
        decision,
        documentation:
          decision === "reject" ? null : documentation,
      });
      if (
        response.data.status === "error" ||
        !["approved", "edited", "rejected"].includes(response.data.status)
      ) {
          setError(response.data.message || "Documentation update failed.");
      } else {
        setMessage(response.data.message || `Suggestion ${decision} completed.`);
      }
    } catch (err) {
      console.error(err);
      setError("Could not submit your decision. Check the backend.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="min-h-screen bg-[#0b1120] p-8 text-slate-100">
      <div className="mx-auto max-w-6xl space-y-8">
        <div>
          <div className="flex items-center gap-3">
            <Sparkles className="text-violet-400" size={28} />
            <h1 className="text-3xl font-bold">AI Documentation Suggestions</h1>
          </div>
          <p className="mt-2 text-slate-400">
            Generate, review, edit, and approve documentation updates.
          </p>
          <p className="mt-2 text-amber-300">
            Selected source code and documentation context are sent to Groq for processing.
          </p>
        </div>

        <section className="rounded-xl border border-slate-700 bg-[#111b2e] p-6">
          <h2 className="mb-5 text-lg font-semibold">Change Details</h2>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="text-sm text-slate-300">
              Repository path
              <input
                value={repositoryPath}
                onChange={(e) => setRepositoryPath(e.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-700 bg-[#0b1120] p-3 text-slate-100"
              />
            </label>

            <label className="text-sm text-slate-300">
              Java file path
              <input
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-700 bg-[#0b1120] p-3"
              />
            </label>

            <label className="text-sm text-slate-300">
              Class name
              <input
                value={className}
                onChange={(e) => setClassName(e.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-700 bg-[#0b1120] p-3"
              />
            </label>

            <label className="text-sm text-slate-300">
              Method name
              <input
                value={methodName}
                onChange={(e) => setMethodName(e.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-700 bg-[#0b1120] p-3"
              />
            </label>

            <label className="text-sm text-slate-300 md:col-span-2">
              Change type
              <select
                value={changeType}
                onChange={(e) => setChangeType(e.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-700 bg-[#0b1120] p-3"
              >
                <option value="">Select a detected change</option>
                <option value="method_added">Method added</option>
                <option value="method_modified">Method modified</option>
                <option value="method_removed">Method removed</option>
              </select>
            </label>
          </div>

          <button
            onClick={generateSuggestion}
            disabled={loading}
            className="mt-6 flex items-center gap-2 rounded-lg bg-violet-600 px-5 py-3 font-medium hover:bg-violet-500 disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="animate-spin" size={18} />
            ) : (
              <Sparkles size={18} />
            )}
            {loading ? "Generating..." : "Generate Suggestion"}
          </button>
        </section>

        {error && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-red-300">
            {error}
          </div>
        )}

        {message && (
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4 text-emerald-300">
            {message}
          </div>
        )}

        {result && (
          <>
            <section className="rounded-xl border border-slate-700 bg-[#111b2e] p-6">
              <h2 className="mb-4 text-lg font-semibold">Change Summary</h2>
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <p className="text-sm text-slate-400">Class</p>
                  <p className="font-medium">{result.class}</p>
                </div>
                <div>
                  <p className="text-sm text-slate-400">Method</p>
                  <p className="font-medium">{result.method}</p>
                </div>
                <div>
                  <p className="text-sm text-slate-400">Change type</p>
                  <p className="font-medium">{result.change_type}</p>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-slate-700 bg-[#111b2e] p-6">
              <div className="mb-4 flex items-center gap-2">
                <FileText className="text-violet-400" />
                <h2 className="text-lg font-semibold">Generated Documentation</h2>
              </div>

              <p className="mb-3 text-sm text-slate-400">
                Target file: {result.target_documentation}
              </p>

              {result.developer_comment && (
                <div className="mb-4 rounded-lg bg-slate-800 p-4">
                  <p className="mb-1 text-xs font-semibold uppercase text-slate-400">
                    Developer comment
                  </p>
                  <p className="text-sm">{result.developer_comment}</p>
                </div>
              )}

              <textarea
                value={documentation}
                onChange={(e) => setDocumentation(e.target.value)}
                rows={12}
                className="w-full rounded-lg border border-slate-700 bg-[#0b1120] p-4 font-mono text-sm leading-6 text-slate-200"
              />

              <p className="mt-2 text-xs text-slate-500">
                You can edit the generated documentation before saving it.
              </p>

              <div className="mt-5 flex flex-wrap gap-3">
                <button
                  onClick={() => submitDecision("approve")}
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-3 font-medium hover:bg-emerald-500 disabled:opacity-50"
                >
                  <CheckCircle size={18} />
                  Approve
                </button>

                <button
                  onClick={() => submitDecision("edit")}
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-3 font-medium hover:bg-blue-500 disabled:opacity-50"
                >
                  <Save size={18} />
                  Edit & Save
                </button>

                <button
                  onClick={() => submitDecision("reject")}
                  disabled={saving}
                  className="flex items-center gap-2 rounded-lg bg-red-600 px-4 py-3 font-medium hover:bg-red-500 disabled:opacity-50"
                >
                  <XCircle size={18} />
                  Reject
                </button>
              </div>

              {saving && (
                <p className="mt-3 text-sm text-slate-400">
                  Submitting your decision...
                </p>
              )}
            </section>

            <section className="rounded-xl border border-slate-700 bg-[#111b2e] p-6">
              <h2 className="mb-4 text-lg font-semibold">Retrieved Documentation Context</h2>
              <div className="space-y-3">
                {result.retrieved_documents.map((doc, index) => (
                  <div
                    key={`${doc.file}-${doc.chunk}-${index}`}
                    className="rounded-lg border border-slate-700 bg-[#0b1120] p-3"
                  >
                    <p className="font-medium">{doc.file}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      Chunk {doc.chunk} · {doc.type}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
