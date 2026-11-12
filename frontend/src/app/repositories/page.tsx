
"use client";
import PageHeader from "../components/PageHeader";
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import Link from "next/link";
import { apiBaseUrl } from "@/lib/apiBaseUrl";
import { isHosted } from "@/lib/deployment";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";
import RepositorySourceSelector from "../components/repository/RepositorySourceSelector";
import {
  FolderGit2,
  Search,
  Trash2,
  ScanSearch,
  ArrowLeft,
  GitBranch,
  CheckCircle2,
  Loader2,
  AlertCircle,
} from "lucide-react";

type Repository = {
  id: number | string;
  name: string;
  path?: string;
  branch?: string;
};

export default function RepositoriesPage() {
  const { setRepositoryPath: selectRepository } = useRepositoryAnalysis();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [repositoryPath, setRepositoryPath] = useState("");
  const [search, setSearch] = useState("");

  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const addingRef = useRef(false);
  const [deletingId, setDeletingId] = useState<number | string | null>(null);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  // Load registered repositories from FastAPI.
  const fetchRepositories = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await axios.get(`${apiBaseUrl}/repositories`);

      setRepositories(response.data.repositories ?? []);
    } catch (err) {
      console.error("Failed to load repositories:", err);
      if (isHosted && axios.isAxiosError(err) && err.response?.status === 401) {
        setError("Your session has expired. Sign in again.");
      } else if (isHosted && axios.isAxiosError(err) && err.response?.status === 403) {
        setError("You do not have permission to access these repositories.");
      } else {
        setError("Could not load repositories. Check whether FastAPI is running.");
      }
    } finally {
      setLoading(false);
    }
  };

  // Load repositories when the page opens.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetchRepositories();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  // Register a repository through FastAPI.
  const addRepository = async () => {
    if (addingRef.current || isHosted) return;
    if (!repositoryPath.trim()) {
      setError("Please enter a repository path.");
      setMessage("");
      return;
    }

    addingRef.current = true;
    try {
      setAdding(true);
      setError("");
      setMessage("");

      const response = await axios.post(`${apiBaseUrl}/repositories`, {
        repository_path: repositoryPath.trim(),
      });

      if (response.data.status !== "success") {
        setError(response.data.message || "Could not register repository.");
        return;
      }

      setMessage(response.data.message);
      setRepositoryPath("");

      await fetchRepositories();
    } catch (err) {
      console.error("Failed to add repository:", err);

      if (axios.isAxiosError(err)) {
        setError(
          err.response?.data?.detail ||
            "Could not register repository. Check the backend connection."
        );
      } else {
        setError("An unexpected error occurred.");
      }
    } finally {
      addingRef.current = false;
      setAdding(false);
    }
  };

  // Delete a repository through FastAPI.
  const removeRepository = async (id: number | string) => {
    const confirmed = window.confirm(
      "Are you sure you want to remove this repository from DocGuard?"
    );

    if (!confirmed) return;

    try {
      setDeletingId(id);
      setError("");
      setMessage("");

      const response = await axios.delete(
        `${apiBaseUrl}/repositories/${id}`
      );

      if (response.data.status !== "success") {
        setError(response.data.message || "Could not remove repository.");
        return;
      }

      setMessage(response.data.message);

      await fetchRepositories();
    } catch (err) {
      console.error("Failed to delete repository:", err);
      setError("Could not remove repository. Please try again.");
    } finally {
      setDeletingId(null);
    }
  };

  // Filter repositories by name or path.
  const filteredRepositories = repositories.filter((repo) =>
    `${repo.name} ${repo.path}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  return (
    
    <main className="min-h-screen bg-[#0b1020] px-5 py-8 text-slate-100 sm:px-8">
      <PageHeader
        eyebrow="Workspace"
        title="Repositories"
        description="Manage your code repositories and monitor documentation changes."
      />
      <div className="mx-auto max-w-6xl">

        {/* Back navigation */}
        <Link
          href="/"
          className="mb-8 inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white"
        >
          <ArrowLeft size={16} />
          Back to Dashboard
        </Link>

        {/* Page heading */}
        <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-3xl font-bold">Repositories</h1>
            <p className="mt-2 text-sm text-slate-400">
              Manage the Git repositories you want DocGuard to analyze.
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#111a2e] px-4 py-2 text-sm text-slate-300">
            <FolderGit2 size={17} className="text-blue-400" />
            {repositories.length} registered
          </div>
        </div>

        <RepositorySourceSelector hosted={isHosted} repositoryPath={repositoryPath}
          onPathChange={setRepositoryPath} onAddLocal={() => void addRepository()} adding={adding} />
        {error && <div role="alert" className="mb-4 flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-300">
          <AlertCircle size={17} className="mt-0.5 shrink-0" />{error}
        </div>}
        {message && <div role="status" className="mb-4 flex items-start gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-300">
          <CheckCircle2 size={17} className="mt-0.5 shrink-0" />{message}
        </div>}

        {/* Repository list */}
        <section className="overflow-hidden rounded-xl border border-white/10 bg-[#111a2e]">
          <div className="flex flex-col justify-between gap-4 border-b border-white/10 p-5 sm:flex-row sm:items-center">
            <div>
              <h2 className="font-semibold">Registered repositories</h2>
              <p className="mt-1 text-xs text-slate-400">
                Repositories retrieved from the DocGuard backend.
              </p>
            </div>

            <div className="relative">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
              />

              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search repositories..."
                className="w-full rounded-lg border border-white/10 bg-[#0b1020] py-2 pl-9 pr-3 text-sm outline-none focus:border-blue-500 sm:w-64"
              />
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center gap-3 px-5 py-12 text-sm text-slate-400">
              <Loader2 size={19} className="animate-spin" />
              Loading repositories...
            </div>
          ) : filteredRepositories.length > 0 ? (
            <div className="divide-y divide-white/5">
              {filteredRepositories.map((repo) => (
                <div
                  key={repo.id}
                  className="flex flex-col justify-between gap-4 p-5 sm:flex-row sm:items-center"
                >
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="rounded-lg bg-blue-500/10 p-3 text-blue-400">
                      <FolderGit2 size={21} />
                    </div>

                    <div className="min-w-0">
                      <h3 className="font-medium">{repo.name}</h3>

                      <p className="mt-1 break-all text-xs text-slate-500">
                        {repo.path || repo.id}
                      </p>

                      <div className="mt-2 flex items-center gap-2 text-xs text-slate-400">
                        <GitBranch size={13} />
                        {repo.branch || "Hosted workspace"}
                      </div>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <Link
                      href="/analysis"
                      onClick={() => selectRepository(isHosted ? String(repo.id) : repo.path || "")}
                      className="flex items-center gap-2 rounded-lg bg-blue-600/15 px-3 py-2 text-xs font-medium text-blue-300 hover:bg-blue-600/25"
                    >
                      <ScanSearch size={15} />
                      Analyze
                    </Link>

                    {!isHosted && <button
                      onClick={() => removeRepository(repo.id)}
                      disabled={deletingId === repo.id}
                      aria-label={`Remove ${repo.name}`}
                      className="rounded-lg border border-white/10 p-2 text-slate-400 hover:border-red-500/30 hover:text-red-400 disabled:opacity-50"
                    >
                      {deletingId === repo.id ? (
                        <Loader2 size={16} className="animate-spin" />
                      ) : (
                        <Trash2 size={16} />
                      )}
                    </button>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="px-5 py-12 text-center">
              <FolderGit2
                size={28}
                className="mx-auto text-slate-500"
              />

              <p className="mt-3 text-sm text-slate-300">
                {search
                  ? "No matching repositories found."
                  : "No repositories registered yet."}
              </p>

              <p className="mt-2 text-xs text-slate-500">
                {search
                  ? "Try a different search term."
                  : isHosted ? "Hosted imports are not yet available." : "Add a Git repository using the form above."}
              </p>
            </div>
          )}
        </section>

        <p className="mt-5 flex items-center gap-2 text-xs text-slate-500">
          <CheckCircle2 size={14} className="text-emerald-400" />
          Repository information is stored by the FastAPI backend.
        </p>
      </div>
    </main>
  );
}
