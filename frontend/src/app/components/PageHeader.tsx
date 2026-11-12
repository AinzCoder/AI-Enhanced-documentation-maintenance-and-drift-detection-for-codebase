
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description: string;
  eyebrow?: string;
  action?: ReactNode;
}

export default function PageHeader({
  title,
  description,
  eyebrow,
  action,
}: PageHeaderProps) {
  return (
    <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">

      {/* Page Information */}
      <div>
        {eyebrow && (
          <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-blue-400">
            {eyebrow}
          </p>
        )}

        <h1 className="text-3xl font-bold tracking-tight text-white">
          {title}
        </h1>

        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
          {description}
        </p>
      </div>

      {/* Optional Action Button or Element */}
      {action && (
        <div className="flex shrink-0 items-center">
          {action}
        </div>
      )}
    </div>
  );
}
