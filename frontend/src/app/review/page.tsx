import Link from "next/link";

export default function ReviewApprovalPage() {
  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-7">
        <h1 className="text-3xl font-semibold tracking-tight">Review & approval</h1>
        <p className="mt-2 text-sm text-slate-600">Review a preview before applying it.</p>
      </header>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="font-semibold">Open a saved preview</h2>
        <p className="mt-2 text-sm text-slate-600">Retrieve it by generation ID, then approve or reject it in the review panel.</p>
        <p className="mt-2 text-sm text-slate-600">Approval verifies the source and target hashes before writing.</p>
        <Link href="/ai-documentation#retrieve-preview" className="mt-5 inline-flex min-h-11 items-center rounded-lg bg-slate-900 px-5 text-sm font-semibold text-white hover:bg-slate-700">
          Retrieve preview
        </Link>
      </section>
    </div>
  );
}
