import * as React from "react";

import { cn } from "@/lib/utils";

export function Table({
  className,
  ...props
}: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-auto">
      <table
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  );
}
export function TableHeader(
  props: React.HTMLAttributes<HTMLTableSectionElement>,
) {
  return <thead className="border-b border-white/8" {...props} />;
}
export function TableBody(
  props: React.HTMLAttributes<HTMLTableSectionElement>,
) {
  return <tbody className="[&_tr:last-child]:border-0" {...props} />;
}
export function TableRow({
  className,
  ...props
}: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        "border-b border-white/6 transition-colors hover:bg-white/[0.025]",
        className,
      )}
      {...props}
    />
  );
}
export function TableHead({
  className,
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "h-11 px-3 text-left align-middle text-[11px] font-semibold uppercase tracking-wider text-slate-500",
        className,
      )}
      {...props}
    />
  );
}
export function TableCell({
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={cn("p-3 align-middle text-slate-300", className)}
      {...props}
    />
  );
}
