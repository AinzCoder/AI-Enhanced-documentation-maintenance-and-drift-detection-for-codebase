
import type { ReactNode } from "react";
import Card from "../components/Card";

interface StatCardProps {
  title: string;
  value: string | number;
  description: string;
  icon?: ReactNode;
}

export default function StatCard({
  title,
  value,
  description,
  icon,
}: StatCardProps) {
  return (
    <Card className="transition duration-200 hover:border-blue-500/40">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">{title}</p>

        {icon && (
          <div className="rounded-lg bg-blue-500/10 p-2 text-blue-400">
            {icon}
          </div>
        )}
      </div>

      <p className="mt-4 text-3xl font-bold tabular-nums text-white">
        {value}
      </p>

      <p className="mt-2 text-xs text-slate-500">
        {description}
      </p>
    </Card>
  );
}
