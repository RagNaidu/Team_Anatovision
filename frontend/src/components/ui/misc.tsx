import * as React from "react";
import { cn } from "@/lib/utils";
import { Info, AlertCircle } from "lucide-react";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton h-4", className)} />;
}

export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("h-9 rounded-md border border-line-strong bg-surface px-2.5 text-[14px] text-ink", className)}
      {...props}
    >
      {children}
    </select>
  );
}

export function Notice({ tone = "info", children, className, action }: { tone?: "info" | "error"; children: React.ReactNode; className?: string; action?: React.ReactNode }) {
  const Icon = tone === "error" ? AlertCircle : Info;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex items-start gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-[14px] text-body-2", className)}>
      <Icon size={16} strokeWidth={1.5} className="mt-[3px] shrink-0 text-muted" aria-hidden />
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

export function Segmented<T extends string | number>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full border border-line-strong bg-surface p-0.5">
      {options.map((o) => (
        <button key={String(o.value)} role="radio" aria-checked={o.value === value} type="button" onClick={() => onChange(o.value)}
          className={cn("h-8 rounded-full px-4 text-[14px] transition-colors duration-150", o.value === value ? "bg-user-bubble text-user-bubble-ink" : "text-body-2 hover:bg-surface-2")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function PageTitle({ children, sub }: { children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="font-serif text-[32px] font-semibold leading-tight text-ink">{children}</h1>
      {sub ? <p className="serif-label mt-1">{sub}</p> : null}
    </div>
  );
}
