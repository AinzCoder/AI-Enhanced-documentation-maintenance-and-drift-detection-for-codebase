"use client";

import Link from "next/link";
import { useRepositoryAnalysis } from "../components/repository/RepositoryAnalysisContext";
import RepositoryPathInput from "../components/repository/RepositoryPathInput";
import { isHosted } from "@/lib/deployment";

export default function RepositoryPage() {
  const { repositoryPath, setRepositoryPath } = useRepositoryAnalysis();
  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-7">
        <h1 className="text-3xl font-semibold tracking-tight">Repository</h1>
        <p className="mt-2 text-sm text-slate-600">{isHosted ? "Choose an authorized hosted repository for this session." : "Choose a local repository for this session."}</p>
      </header>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <RepositoryPathInput value={repositoryPath} onChange={setRepositoryPath} />
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <Link href="/analysis" className="inline-flex min-h-11 items-center rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-cyan-600">
            Continue to analysis
          </Link>
          <Link href="/repositories" className="text-sm font-medium text-cyan-800 hover:underline">
            Manage registered repositories
          </Link>
        </div>
      </section>
    </div>
  );
}
