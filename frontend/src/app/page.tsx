"use client";

import { ArrowRight, BookOpenCheck, FileSearch2, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { checkBackendHealth, getApiErrorMessage } from "@/lib/api";
import { useRepositoryAnalysis } from "./components/repository/RepositoryAnalysisContext";

export default function Dashboard() {
  const { repositoryPath } = useRepositoryAnalysis();
  const [status, setStatus] = useState("Checking");
  const [detail, setDetail] = useState("");

  useEffect(() => {
    let active = true;
    checkBackendHealth()
      .then(() => { if (active) setStatus("Connected"); })
      .catch((error: unknown) => {
        if (active) {
          setStatus("Unavailable");
          setDetail(getApiErrorMessage(error));
        }
      });
    return () => { active = false; };
  }, []);

  const nextHref = repositoryPath.trim() ? "/analysis" : "/repository";
  return (
    <div className="mx-auto max-w-7xl">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-10">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-cyan-700">DocGuard workspace</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">Keep documentation in sync.</h1>
            <p className="mt-3 text-sm text-slate-600">Analyze your repository, generate a preview, and review changes.</p>
          </div>
          <span role="status" className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">Backend: {status}</span>
        </div>
        {detail && <p className="mt-4 text-sm text-rose-700">{detail}</p>}
        <Link href={nextHref} className="mt-7 inline-flex min-h-11 items-center gap-2 rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white hover:bg-slate-700 focus-visible:outline-2 focus-visible:outline-cyan-600">
          {repositoryPath.trim() ? "Analyze repository" : "Select repository"}
          <ArrowRight aria-hidden="true" size={16} />
        </Link>
      </section>
      <section aria-label="Workspace tools" className="mt-6 grid gap-4 md:grid-cols-3">
        {[
          { title: "Analyze", description: "Explore Java files and methods.", href: "/analysis", icon: FileSearch2 },
          { title: "Coverage & drift", description: "Find missing or changed documentation.", href: "/drift", icon: BookOpenCheck },
          { title: "Generate & review", description: "Preview documentation before approval.", href: "/ai-documentation", icon: Sparkles },
        ].map(({ title, description, href, icon: Icon }) => (
          <Link key={href} href={href} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:border-cyan-400 focus-visible:outline-2 focus-visible:outline-cyan-600">
            <Icon aria-hidden="true" className="text-cyan-700" size={21} />
            <h2 className="mt-4 font-semibold text-slate-900">{title}</h2>
            <p className="mt-1 text-sm text-slate-600">{description}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
