import type { AnalysisMode } from "@/types/api";

interface AnalysisModeSelectorProps {
  value: AnalysisMode;
  onChange: (mode: AnalysisMode) => void;
  disabled?: boolean;
}

const modes: Array<{ value: AnalysisMode; label: string }> = [
  { value: "full", label: "Full Repository Analysis" },
  { value: "working_tree", label: "Git Working Tree Changes" },
  { value: "commits", label: "Git Commit Comparison" },
];

export default function AnalysisModeSelector({
  value,
  onChange,
  disabled = false,
}: AnalysisModeSelectorProps) {
  return (
    <div>
      <label
        htmlFor="analysis-mode"
        className="mb-2 block text-sm font-medium text-slate-800"
      >
        Analysis mode
      </label>
      <select
        id="analysis-mode"
        value={value}
        onChange={(event) => {
          const selected = modes.find(
            (mode) => mode.value === event.target.value
          );
          if (selected) {
            onChange(selected.value);
          }
        }}
        disabled={disabled}
        className="min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10 disabled:cursor-not-allowed disabled:bg-slate-100"
      >
        {modes.map((mode) => (
          <option key={mode.value} value={mode.value}>
            {mode.label}
          </option>
        ))}
      </select>
    </div>
  );
}
