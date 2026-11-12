import { apiClient } from "@/lib/api";

export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-7">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-sm text-slate-600">Current connection settings.</p>
      </header>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="font-semibold">Backend API</h2>
        <p className="mt-2 break-all font-mono text-sm text-slate-700">{apiClient.defaults.baseURL}</p>
        <p className="mt-3 text-sm text-slate-600">Configure the address with NEXT_PUBLIC_API_BASE_URL when starting the frontend.</p>
      </section>
    </div>
  );
}
