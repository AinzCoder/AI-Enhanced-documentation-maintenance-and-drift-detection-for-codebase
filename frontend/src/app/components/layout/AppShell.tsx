"use client";

import {
  Activity,
  FileText,
  FolderSearch2,
  FolderGit2,
  Menu,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useRepositoryAnalysis } from "../repository/RepositoryAnalysisContext";

const navigation = [
  { label: "Dashboard", href: "/", icon: Activity, paths: ["/"] },
  { label: "Repository", href: "/repository", icon: FolderGit2, paths: ["/repository", "/repositories"] },
  { label: "Analysis", href: "/analysis", icon: FolderSearch2, paths: ["/analysis", "/drift", "/rag"] },
  { label: "AI Documentation", href: "/ai-documentation", icon: FileText, paths: ["/ai-documentation", "/review", "/history", "/suggestions"] },
  { label: "Settings", href: "/settings", icon: Settings, paths: ["/settings"] },
];

const analysisLinks = [
  { label: "Repository analysis", href: "/analysis" },
  { label: "Coverage & Git drift", href: "/drift" },
  { label: "Search index", href: "/rag" },
];
const documentationLinks = [
  { label: "Generate & review", href: "/ai-documentation" },
  { label: "Review", href: "/review" },
  { label: "History", href: "/history" },
  { label: "Change suggestions", href: "/suggestions" },
];

function NavigationLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav aria-label="Primary navigation" className="space-y-1">
      {navigation.map(({ label, href, icon: Icon, paths }) => {
        const active = paths.some((path) => pathname === path || (path !== "/" && pathname.startsWith(`${path}/`)));

        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-cyan-400 ${
              active
                ? "bg-cyan-400/10 text-cyan-300"
                : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
            }`}
          >
            <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function WorkspaceNavigation() {
  const pathname = usePathname();
  const { repositoryPath } = useRepositoryAnalysis();
  const sections = analysisLinks.some((item) => item.href === pathname)
    ? analysisLinks
    : documentationLinks.some((item) => item.href === pathname)
      ? documentationLinks
      : [];
  const steps = [
    { label: "Select Repository", href: "/repository" },
    { label: "Analyze", href: "/analysis" },
    { label: "Generate", href: "/ai-documentation" },
    { label: "Review", href: "/review" },
  ];

  return (
    <div className="border-b border-slate-200 bg-white px-4 py-4 sm:px-7 lg:px-10">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav aria-label="Documentation workflow">
            <ol className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs font-medium text-slate-600">
              {steps.map((step, index) => (
                <li key={step.href} className="flex items-center gap-2">
                  {index > 0 && <span aria-hidden="true" className="text-slate-300">→</span>}
                  <Link href={step.href} className="rounded text-slate-700 hover:text-cyan-700 focus-visible:outline-2 focus-visible:outline-cyan-600">
                    {step.label}
                  </Link>
                </li>
              ))}
            </ol>
          </nav>
          <Link href="/repository" className="max-w-full truncate rounded text-xs text-slate-600 hover:text-cyan-700 focus-visible:outline-2 focus-visible:outline-cyan-600" title={repositoryPath || "No repository selected"}>
            <span className="font-semibold">Repository: </span>
            {repositoryPath || "Not selected"}
          </Link>
        </div>
        {sections.length > 0 && (
          <nav aria-label={sections === analysisLinks ? "Analysis sections" : "Documentation sections"} className="mt-4 flex flex-wrap gap-2">
            {sections.map((item) => (
              <Link key={item.href} href={item.href} aria-current={pathname === item.href ? "page" : undefined}
                className={`rounded-lg px-3 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-cyan-600 ${pathname === item.href ? "bg-cyan-50 text-cyan-800" : "text-slate-600 hover:bg-slate-100"}`}>
                {item.label}
              </Link>
            ))}
          </nav>
        )}
      </div>
    </div>
  );
}

function Brand({ lightBackground = false }: { lightBackground?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-3 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-cyan-400">
      <span className="flex size-10 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300">
        <ShieldCheck aria-hidden="true" size={22} />
      </span>
      <span>
        <span className={`block text-base font-semibold tracking-tight ${lightBackground ? "text-slate-950" : "text-white"}`}>
          DocGuard
        </span>
        <span className="block text-xs text-slate-500">
          Documentation intelligence
        </span>
      </span>
    </Link>
  );
}

export default function AppShell({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-800 bg-[#101923] px-4 py-6 lg:flex">
        <div className="mb-10 px-2">
          <Brand />
        </div>
        <p className="mb-3 px-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          Workspace
        </p>
        <NavigationLinks />
      </aside>

      <div className="min-h-screen lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur sm:px-7 lg:hidden">
          <Brand lightBackground />
          <button
            type="button"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={menuOpen}
            aria-controls="mobile-primary-navigation"
            onClick={() => setMenuOpen((open) => !open)}
            className="inline-flex size-10 items-center justify-center rounded-lg border border-slate-200 text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600"
          >
            {menuOpen ? (
              <X aria-hidden="true" size={19} />
            ) : (
              <Menu aria-hidden="true" size={19} />
            )}
          </button>
        </header>

        {menuOpen && (
          <>
            <button
              type="button"
              aria-label="Close navigation menu"
              onClick={() => setMenuOpen(false)}
              className="fixed inset-0 z-30 cursor-default bg-slate-950/40 lg:hidden"
            />
            <aside
              id="mobile-primary-navigation"
              className="fixed inset-y-0 left-0 z-40 flex w-[min(20rem,85vw)] flex-col border-r border-slate-800 bg-[#101923] px-4 py-6 shadow-2xl lg:hidden"
            >
              <div className="mb-10 flex items-center justify-between px-2">
                <Brand />
                <button
                  type="button"
                  aria-label="Close navigation"
                  onClick={() => setMenuOpen(false)}
                  className="rounded-lg p-2 text-slate-400 outline-none hover:bg-white/5 hover:text-white focus-visible:ring-2 focus-visible:ring-cyan-400"
                >
                  <X aria-hidden="true" size={18} />
                </button>
              </div>
              <p className="mb-3 px-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                Workspace
              </p>
              <NavigationLinks onNavigate={() => setMenuOpen(false)} />
            </aside>
          </>
        )}

        <WorkspaceNavigation />
        <main className="min-h-[calc(100vh-4rem)] px-4 py-7 sm:px-7 sm:py-9 lg:px-10 lg:py-10">
          {children}
        </main>
      </div>
    </div>
  );
}
