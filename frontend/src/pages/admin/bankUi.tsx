import type { BankStatus, BankUse } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS: Record<BankStatus, string> = { draft: "bg-warn-soft text-warn", approved: "bg-ok-soft text-ok", retired: "bg-surface-2 text-muted" };
export function StatusPill({ status }: { status: BankStatus }) {
  return <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-[12px] font-medium capitalize", STATUS[status])}>{status}</span>;
}
export function UsePill({ use }: { use: BankUse }) {
  return <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-[12px] font-medium", use === "exam_secure" ? "bg-accent-soft text-accent-soft-ink" : "bg-surface-2 text-body-2")}>{use === "exam_secure" ? "Exam-secure" : "Practice"}</span>;
}
export const SOURCE_LABEL: Record<string, string> = { instructor: "Instructor", ai: "AI", web: "Web", imported: "Imported" };
