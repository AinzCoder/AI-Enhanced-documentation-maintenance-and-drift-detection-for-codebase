
import type { ReactNode } from "react";

type AlertType = "success" | "error" | "warning" | "info";

interface AlertProps {
  type: AlertType;
  children: ReactNode;
}

const alertStyles: Record<AlertType, string> = {
  success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  error: "border-red-500/30 bg-red-500/10 text-red-400",
  warning: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  info: "border-blue-500/30 bg-blue-500/10 text-blue-400",
};

export default function Alert({ type, children }: AlertProps) {
  return (
    <div
      role={type === "error" ? "alert" : "status"}
      className={`rounded-lg border px-4 py-3 text-sm ${alertStyles[type]}`}
    >
      {children}
    </div>
  );
}
