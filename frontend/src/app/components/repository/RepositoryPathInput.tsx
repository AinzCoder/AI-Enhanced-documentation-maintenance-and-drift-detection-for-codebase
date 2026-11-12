interface RepositoryPathInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export default function RepositoryPathInput({
  value,
  onChange,
  disabled = false,
}: RepositoryPathInputProps) {
  return (
    <div>
      <label
        htmlFor="repository-path"
        className="mb-2 block text-sm font-medium text-slate-800"
      >
        Local repository path
      </label>
      <input
        id="repository-path"
        name="repository_path"
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={String.raw`For example, D:\Projects\MyJavaRepository`}
        autoComplete="off"
        spellCheck={false}
        disabled={disabled}
        aria-describedby="repository-path-help"
        className="min-h-12 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-600/10 disabled:cursor-not-allowed disabled:bg-slate-100"
      />
      <p id="repository-path-help" className="mt-2 text-xs leading-5 text-slate-500">
        The path is sent to your local FastAPI backend, which reads the
        repository. Your browser cannot browse local folders.
      </p>
    </div>
  );
}
