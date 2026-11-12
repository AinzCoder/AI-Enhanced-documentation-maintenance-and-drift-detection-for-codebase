
import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  children: ReactNode;
}

export default function Button({
  variant = "primary",
  children,
  className = "",
  ...props
}: ButtonProps) {
  const styles: Record<ButtonVariant, string> = {
    primary: "bg-blue-600 text-white hover:bg-blue-500",
    secondary: "border border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700",
    danger: "bg-red-600 text-white hover:bg-red-500",
    ghost: "text-slate-300 hover:bg-slate-800",
  };

  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}
