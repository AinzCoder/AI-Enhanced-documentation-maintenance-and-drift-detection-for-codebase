import type { LucideIcon } from "lucide-react";
import { ArrowUpRight, CircleDashed } from "lucide-react";

interface WorkflowPlaceholderProps {
  eyebrow: string;
  title: string;
  description: string;
  icon: LucideIcon;
}

export default function WorkflowPlaceholder({
  eyebrow,
  title,
  description,
  icon: Icon,
}: WorkflowPlaceholderProps) {
  return (
    <section className="mx-auto max-w-5xl">
      <div className="mb-8 flex items-start gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-cyan-50 text-cyan-700">
          <Icon aria-hidden="true" size={23} strokeWidth={1.8} />
        </span>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">
            {eyebrow}
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
            {title}
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            {description}
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500">
            <CircleDashed aria-hidden="true" size={21} />
          </span>
          <div className="min-w-0">
            <h2 className="font-medium text-slate-900">
              Workflow not configured
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              This workspace is a navigation shell. No repository has been
              analyzed and no index, preview, or approval action has been
              started.
            </p>
          </div>
        </div>
        <div className="mt-6 flex items-center gap-2 border-t border-slate-100 pt-5 text-xs text-slate-500">
          <ArrowUpRight aria-hidden="true" size={15} />
          Interactive workflows will be added in a later phase.
        </div>
      </div>
    </section>
  );
}
