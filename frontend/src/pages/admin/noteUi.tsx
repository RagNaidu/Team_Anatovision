import type { NoteStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE: Record<NoteStatus, string> = {
  published: "bg-ok-soft text-ok",
  ready: "bg-warn-soft text-warn",
  processing: "bg-warn-soft text-warn",
  draft: "bg-surface-2 text-body-2",
  archived: "bg-surface-2 text-muted",
};
export const STATUS_LABEL: Record<NoteStatus, string> = { published: "Published", ready: "Ready", processing: "Processing", draft: "Draft", archived: "Archived" };

export function StatusChip({ status, className }: { status: NoteStatus; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-[12px] font-medium", TONE[status], className)}>{STATUS_LABEL[status]}</span>;
}

export const DIFF_LABEL: Record<string, string> = { unchanged: "Unchanged", edited: "Edited", rewritten: "Rewritten", added: "Added", removed: "Removed" };
export const DIFF_TONE: Record<string, string> = {
  edited: "bg-warn-soft text-warn", rewritten: "bg-warn-soft text-warn", added: "bg-ok-soft text-ok", removed: "bg-accent-soft text-accent-soft-ink", unchanged: "bg-surface-2 text-muted",
};
