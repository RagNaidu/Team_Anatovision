import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Notice } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";

export function AdminFrame({ title, sub, children, wide }: { title: string; sub?: ReactNode; children: ReactNode; wide?: boolean }) {
  return (
    <div className="min-h-full">
      <div className={cn("mx-auto w-full px-6 py-8 max-lg:px-4", wide ? "max-w-[1200px]" : "max-w-[960px]")}>
        <div className="mb-6">
          <h1 className="font-serif text-[32px] font-semibold leading-tight">{title}</h1>
          {sub && <p className="serif-label mt-1">{sub}</p>}
        </div>
        {children}
      </div>
    </div>
  );
}
export function ErrorLine({ message, retry }: { message: string; retry?: () => void }) {
  return <Notice tone="error" action={retry ? <Button size="sm" variant="outline" onClick={retry}>Try again</Button> : undefined}>{message}</Notice>;
}
export function Pager({ page, total, per = 25, onPage }: { page: number; total: number; per?: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / per));
  if (pages <= 1) return null;
  return (
    <div className="mt-4 flex items-center justify-between text-[14px] text-muted">
      <span>Page {page} of {pages}</span>
      <div className="flex gap-2">
        <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}
