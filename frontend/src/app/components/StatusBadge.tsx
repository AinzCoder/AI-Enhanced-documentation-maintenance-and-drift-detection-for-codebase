
type Status =
  | "success"
  | "pending"
  | "failed"
  | "drift"
  | "approved"
  | "rejected"
  | "active";

interface StatusBadgeProps {
  status: Status;
}

const statusStyles: Record<Status, string> = {
  success: "bg-emerald-500/10 text-emerald-400",
  pending: "bg-amber-500/10 text-amber-400",
  failed: "bg-red-500/10 text-red-400",
  drift: "bg-orange-500/10 text-orange-400",
  approved: "bg-emerald-500/10 text-emerald-400",
  rejected: "bg-red-500/10 text-red-400",
  active: "bg-blue-500/10 text-blue-400",
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold capitalize ${statusStyles[status]}`}
    >
      {status}
    </span>
  );
}
