"use client";

import {
  AlertCircle,
  CheckCircle2,
  LoaderCircle,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  approveGeneration,
  getApiErrorMessage,
  getGeneration,
  rejectGeneration,
} from "@/lib/api";
import type {
  ApprovalResponse,
  GenerationAudit,
  GenerationRecord,
} from "@/types/api";

type Decision = "approve" | "reject";

interface ActionOutcome {
  kind: "success" | "error" | "indeterminate";
  title: string;
  message: string;
  response?: ApprovalResponse;
}

function isTerminalStatus(status: string): boolean {
  return ["approved", "rejected", "stale", "failed"].includes(status);
}

function hashOutcome(audit: GenerationAudit | undefined): string | null {
  if (!audit) {
    return null;
  }
  if (audit.status === "approved") {
    return audit.documentation_hash_after !== audit.documentation_hash_before
      ? "The approval audit shows that the target file content changed."
      : "Approval succeeded; the target hash did not change, so the audit does not indicate a content modification.";
  }
  if (audit.status === "rejected") {
    return "The rejection audit records a rejected preview; rejection does not modify documentation files.";
  }
  return audit.failure_reason ?? null;
}

function safeErrorMessage(error: unknown): string {
  const message = getApiErrorMessage(error);
  return /Traceback \(most recent call last\):/.test(message) ||
    /File ".*", line \d+/.test(message)
    ? "The backend reported an internal error. See the FastAPI logs for details."
    : message;
}

function Dialog({
  decision,
  repositoryPath,
  record,
  working,
  onCancel,
  onConfirm,
}: {
  decision: Decision;
  repositoryPath: string;
  record: GenerationRecord;
  working: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmRef.current?.focus();
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !working) {
        event.preventDefault();
        onCancel();
      }
      if (event.key !== "Tab" || !dialogRef.current) {
        return;
      }
      const controls = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );
      if (controls.length === 0) {
        return;
      }
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onCancel, working]);

  const approving = decision === "approve";
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="generation-confirmation-title"
        aria-describedby="generation-confirmation-description"
        className="w-full max-w-xl rounded-2xl bg-white p-5 shadow-2xl sm:p-7"
      >
        <div className="flex items-start gap-3">
          <span
            className={`mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl ${
              approving
                ? "bg-amber-100 text-amber-800"
                : "bg-slate-100 text-slate-700"
            }`}
          >
            {approving ? (
              <ShieldAlert aria-hidden="true" size={20} />
            ) : (
              <ThumbsDown aria-hidden="true" size={19} />
            )}
          </span>
          <div className="min-w-0">
            <h2
              id="generation-confirmation-title"
              className="text-lg font-semibold text-slate-950"
            >
              {approving ? "Approve documentation update?" : "Reject this preview?"}
            </h2>
            <p
              id="generation-confirmation-description"
              className="mt-2 text-sm leading-6 text-slate-600"
            >
              {approving
                ? "Approval may modify the target Markdown file. The backend will verify the stored source and target hashes before writing."
                : "Rejection marks this preview rejected. The backend does not modify repository documentation for a rejection."}
            </p>
          </div>
        </div>

        <dl className="mt-5 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
          {[
            ["Repository", repositoryPath],
            ["Target Markdown file", record.documentation_target],
            ["Generation ID", record.generation_id],
          ].map(([label, value]) => (
            <div key={label} className="grid gap-1 sm:grid-cols-[9rem_1fr] sm:gap-3">
              <dt className="font-medium text-slate-600">{label}</dt>
              <dd className="break-all font-mono text-xs leading-5 text-slate-900">
                {value}
              </dd>
            </div>
          ))}
        </dl>

        <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={working}
            className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            disabled={working}
            className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold text-white outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:cursor-wait disabled:opacity-70 ${
              approving
                ? "bg-amber-700 hover:bg-amber-800 focus-visible:ring-amber-600"
                : "bg-slate-800 hover:bg-slate-900 focus-visible:ring-slate-600"
            }`}
          >
            {working ? (
              <LoaderCircle
                aria-hidden="true"
                size={16}
                className="animate-spin"
              />
            ) : approving ? (
              <ThumbsUp aria-hidden="true" size={16} />
            ) : (
              <ThumbsDown aria-hidden="true" size={16} />
            )}
            {working
              ? "Submitting…"
              : approving
                ? "Confirm approval"
                : "Confirm rejection"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function GenerationReviewPanel({
  initialRecord,
  repositoryPath,
  generatedMarkdown,
  verifyRepositoryIdentity,
  onRecordUpdated,
}: {
  initialRecord: GenerationRecord;
  repositoryPath: string;
  generatedMarkdown: string;
  verifyRepositoryIdentity: (
    repositoryPath: string
  ) => Promise<string | null>;
  onRecordUpdated: (record: GenerationRecord) => void;
}) {
  const [record, setRecord] = useState(initialRecord);
  const [dialogDecision, setDialogDecision] = useState<Decision | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isOperating, setIsOperating] = useState(false);
  const [operationError, setOperationError] = useState("");
  const [outcome, setOutcome] = useState<ActionOutcome | null>(null);
  const requestId = useRef(0);

  async function fetchVerifiedRecord(): Promise<GenerationRecord | null> {
    const refreshed = await getGeneration(record.generation_id);
    if (
      !refreshed ||
      refreshed.generation_id !== record.generation_id ||
      typeof refreshed.repository_identity !== "string"
    ) {
      throw new Error("The backend returned an incomplete generation record.");
    }
    const selectedIdentity = await verifyRepositoryIdentity(repositoryPath);
    if (!selectedIdentity) {
      throw new Error(
        "Repository identity could not be calculated; no action is allowed."
      );
    }
    if (refreshed.repository_identity !== selectedIdentity) {
      throw new Error(
        "The generation belongs to a different repository identity."
      );
    }
    setRecord(refreshed);
    onRecordUpdated(refreshed);
    return refreshed;
  }

  async function requestConfirmation(decision: Decision) {
    if (
      isRefreshing ||
      isOperating ||
      outcome?.kind === "indeterminate"
    ) {
      return;
    }
    setOperationError("");
    setOutcome(null);
    setIsRefreshing(true);
    try {
      const refreshed = await fetchVerifiedRecord();
      if (!refreshed) {
        return;
      }
      if (refreshed.status !== "pending") {
        setOperationError(
          `The backend record is not pending (current status: ${refreshed.status}). No action was sent.`
        );
        return;
      }
      if (
        decision === "approve" &&
        (!refreshed.generation_id ||
          !refreshed.documentation_target ||
          !refreshed.generated_markdown?.trim())
      ) {
        setOperationError(
          "Approval requires a persisted ID, target path, and nonempty generated Markdown."
        );
        return;
      }
      setDialogDecision(decision);
    } catch (error: unknown) {
      setOperationError(safeErrorMessage(error));
    } finally {
      setIsRefreshing(false);
    }
  }

  async function refreshUncertainStatus() {
    if (isRefreshing || isOperating) {
      return;
    }
    setIsRefreshing(true);
    setOperationError("");
    try {
      const refreshed = await fetchVerifiedRecord();
      if (!refreshed) {
        return;
      }
      setOutcome({
        kind: "success",
        title: "Persisted status refreshed",
        message:
          refreshed.status === "pending"
            ? "The backend currently reports pending. This was a read-only refresh, not a retry; a new action requires a separate confirmation."
            : `The backend currently reports “${refreshed.status}”.`,
      });
    } catch (error: unknown) {
      setOperationError(safeErrorMessage(error));
    } finally {
      setIsRefreshing(false);
    }
  }

  async function submitDecision() {
    const decision = dialogDecision;
    if (!decision || isOperating || isRefreshing) {
      return;
    }
    const operationId = ++requestId.current;
    const expectedStatus = decision === "approve" ? "approved" : "rejected";
    setDialogDecision(null);
    setIsOperating(true);
    setOperationError("");
    setOutcome(null);

    try {
      const response =
        decision === "approve"
          ? await approveGeneration(record.generation_id, { decision: "approve" })
          : await rejectGeneration(record.generation_id, { decision: "reject" });
      if (
        !response ||
        response.generation_id !== record.generation_id ||
        typeof response.status !== "string" ||
        typeof response.documentation_target !== "string"
      ) {
        setOutcome({
          kind: "indeterminate",
          title: "Action result is unclear",
          message:
            "The backend response was incomplete. The action was not retried; checking the persisted status.",
        });
      } else {
        const statusMatches =
          response.status === expectedStatus;
        setOutcome({
          kind: statusMatches ? "success" : "error",
          title: statusMatches
            ? decision === "approve"
              ? "Approval completed"
              : "Preview rejected"
            : "Backend returned a non-success status",
          message: statusMatches
            ? `The backend reports status “${response.status}” for ${response.documentation_target}.`
            : `The backend reports status “${response.status}”. No success is claimed.`,
          response,
        });
      }
    } catch (error: unknown) {
      const message = safeErrorMessage(error);
      setOutcome({
        kind: "indeterminate",
        title: "Action outcome is not yet confirmed",
        message: `The request may have reached the backend. It was not retried. ${message} The persisted record is being checked.`,
      });
    }

    try {
      const refreshed = await fetchVerifiedRecord();
      if (operationId !== requestId.current) {
        return;
      }
      if (!refreshed) {
        return;
      }
      if (refreshed.status === "approved" || refreshed.status === "rejected") {
        const auditResult = hashOutcome(refreshed.audit);
        setOutcome((current) => ({
          kind:
            refreshed.status === expectedStatus
              ? "success"
              : current?.kind === "indeterminate"
                ? "indeterminate"
                : "error",
          title:
            refreshed.status === expectedStatus
              ? decision === "approve"
                ? "Approval status verified"
                : "Rejection status verified"
              : "Persisted status differs from the requested action",
          message: [
            `The persisted backend status is “${refreshed.status}”.`,
            `Target: ${refreshed.documentation_target}.`,
            auditResult,
          ]
            .filter(Boolean)
            .join(" "),
          response: current?.response,
        }));
      } else if (refreshed.status === "stale" || refreshed.status === "failed") {
        setOutcome({
          kind: "error",
          title:
            refreshed.status === "stale"
              ? "Preview is stale; approval was blocked"
              : "Backend recorded an operation failure",
          message:
            refreshed.failure_reason ??
            refreshed.audit?.failure_reason ??
            `The persisted backend status is “${refreshed.status}”.`,
        });
      } else if (refreshed.status === "pending") {
        setOutcome((current) =>
          current?.kind === "indeterminate"
            ? {
                ...current,
                message:
                  "The backend record is still pending. The request outcome could not be confirmed; do not retry until you have reviewed the backend status.",
              }
            : {
                kind: "error",
                title: "The decision did not change the persisted status",
                message:
                  "The generation remains pending. No automatic retry was made.",
              }
        );
      } else {
        setOutcome({
          kind: "indeterminate",
          title: "Backend operation is still in progress",
          message: `The persisted status is “${refreshed.status}”. No second action was sent.`,
        });
      }
    } catch (error: unknown) {
      if (operationId === requestId.current) {
        setOutcome((current) => ({
          kind: "indeterminate",
          title: "Could not verify the final status",
          message: `${current?.message ?? "The action response was received."} A read-only status refresh also failed: ${safeErrorMessage(error)}`,
          response: current?.response,
        }));
      }
    } finally {
      if (operationId === requestId.current) {
        setIsOperating(false);
      }
    }
  }

  const markdownAvailable = generatedMarkdown.trim().length > 0;
  const canApprove =
    record.generation_id.length > 0 &&
    record.status === "pending" &&
    markdownAvailable &&
    record.documentation_target.trim().length > 0 &&
    outcome?.kind !== "indeterminate" &&
    !isOperating &&
    !isRefreshing;
  const canReject =
    record.generation_id.length > 0 &&
    record.status === "pending" &&
    outcome?.kind !== "indeterminate" &&
    !isOperating &&
    !isRefreshing;
  const terminal = isTerminalStatus(record.status);

  return (
    <>
      <section
        aria-labelledby="generation-review-heading"
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
      >
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2
              id="generation-review-heading"
              className="text-lg font-semibold text-slate-950"
            >
              Developer review
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-600">
              Actions are available only for a repository-verified, currently
              pending backend record. Backend hash checks remain authoritative;
              eligibility here does not guarantee approval will succeed.
            </p>
          </div>
          <span className="inline-flex w-fit rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
            Backend status: {record.status}
          </span>
        </div>

        <dl className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
            <dt className="text-xs font-medium text-slate-500">Target</dt>
            <dd className="mt-1 break-all font-mono text-sm text-slate-900">
              {record.documentation_target}
            </dd>
          </div>
          <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
            <dt className="text-xs font-medium text-slate-500">Generation ID</dt>
            <dd className="mt-1 break-all font-mono text-xs text-slate-900">
              {record.generation_id}
            </dd>
          </div>
        </dl>

        {record.failure_reason && (
          <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm leading-6 text-rose-900">
            {record.failure_reason}
          </p>
        )}

        <div className="mt-5 flex flex-col gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs leading-5 text-slate-500">
            {terminal
              ? "This generation is terminal and cannot be approved or rejected again."
              : record.status === "processing"
                ? "The backend is processing a decision. Refresh the record before taking further action."
                : "The backend will re-check source and target hashes when approval is submitted."}
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => void requestConfirmation("reject")}
              disabled={!canReject}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 px-4 text-sm font-medium text-slate-700 outline-none hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-slate-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ThumbsDown aria-hidden="true" size={16} />
              Reject preview
            </button>
            <button
              type="button"
              onClick={() => void requestConfirmation("approve")}
              disabled={!canApprove}
              className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-cyan-800 px-4 text-sm font-semibold text-white outline-none hover:bg-cyan-900 focus-visible:ring-2 focus-visible:ring-cyan-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ThumbsUp aria-hidden="true" size={16} />
              Approve update
            </button>
          </div>
        </div>
        {isRefreshing && (
          <p role="status" className="mt-3 flex items-center gap-2 text-sm text-slate-600">
            <LoaderCircle aria-hidden="true" size={15} className="animate-spin" />
            Refreshing persisted status before opening confirmation…
          </p>
        )}
        {isOperating && (
          <p role="status" className="mt-3 flex items-center gap-2 text-sm text-cyan-900">
            <LoaderCircle aria-hidden="true" size={15} className="animate-spin" />
            Submitting the explicit decision and checking its persisted status…
          </p>
        )}
        {operationError && (
          <div
            role="alert"
            className="mt-4 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm leading-6 text-rose-900"
          >
            <AlertCircle aria-hidden="true" size={17} className="mt-1 shrink-0" />
            <p>{operationError}</p>
          </div>
        )}
        {outcome && (
          <div
            role={outcome.kind === "success" ? "status" : "alert"}
            className={`mt-4 flex items-start gap-3 rounded-xl border p-4 text-sm leading-6 ${
              outcome.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-950"
                : outcome.kind === "error"
                  ? "border-rose-200 bg-rose-50 text-rose-950"
                  : "border-amber-200 bg-amber-50 text-amber-950"
            }`}
          >
            {outcome.kind === "success" ? (
              <CheckCircle2 aria-hidden="true" size={18} className="mt-1 shrink-0" />
            ) : (
              <AlertCircle aria-hidden="true" size={18} className="mt-1 shrink-0" />
            )}
            <div>
              <p className="font-semibold">{outcome.title}</p>
              <p className="mt-1 break-words">{outcome.message}</p>
              {outcome.response?.audit?.failure_reason && (
                <p className="mt-2 break-words">
                  Backend audit: {outcome.response.audit.failure_reason}
                </p>
              )}
              {outcome.response?.audit && (
                <AuditSummary audit={outcome.response.audit} />
              )}
              {record.status === "stale" && (
                <a
                  href="#generation-configuration"
                  className="mt-3 inline-flex min-h-9 items-center rounded-md border border-current/30 px-3 text-sm font-medium underline underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-cyan-600"
                >
                  Configure a new preview
                </a>
              )}
              {record.status === "approved" && (
                <Link
                  href="/drift"
                  className="mt-3 inline-flex min-h-9 items-center rounded-md border border-current/30 px-3 text-sm font-medium underline underline-offset-2 outline-none focus-visible:ring-2 focus-visible:ring-cyan-600"
                >
                  Reanalyze coverage
                </Link>
              )}
            </div>
          </div>
        )}
        {outcome?.kind === "indeterminate" && (
          <button
            type="button"
            onClick={() => void refreshUncertainStatus()}
            disabled={isOperating || isRefreshing}
            className="mt-4 inline-flex min-h-10 items-center justify-center rounded-lg border border-amber-300 px-4 text-sm font-medium text-amber-950 outline-none hover:bg-amber-100 focus-visible:ring-2 focus-visible:ring-amber-600 focus-visible:ring-offset-2 disabled:opacity-60"
          >
            Refresh status before any further action
          </button>
        )}
      </section>

      {dialogDecision && (
        <Dialog
          decision={dialogDecision}
          repositoryPath={repositoryPath}
          record={record}
          working={isOperating}
          onCancel={() => setDialogDecision(null)}
          onConfirm={() => void submitDecision()}
        />
      )}
    </>
  );
}

function AuditSummary({ audit }: { audit: GenerationAudit }) {
  return (
    <details className="mt-3 rounded-lg border border-current/20">
      <summary className="cursor-pointer px-3 py-2 font-medium outline-none focus-visible:ring-2 focus-visible:ring-cyan-600">
        Backend audit details
      </summary>
      <dl className="grid gap-2 border-t border-current/20 p-3 sm:grid-cols-2">
        {[
          ["Event", audit.event_type],
          ["Timestamp", audit.timestamp],
          ["Status", audit.status],
          ["Target", audit.documentation_target],
          ["Hash before", audit.documentation_hash_before],
          ["Hash after", audit.documentation_hash_after],
          ["Failure reason", audit.failure_reason],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs font-medium opacity-70">{label}</dt>
            <dd className="break-all font-mono text-xs">{value ?? "Not available"}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
