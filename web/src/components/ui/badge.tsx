import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const variants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider",
  {
    variants: {
      variant: {
        default: "border-cyan-400/20 bg-cyan-400/10 text-cyan-200",
        success: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
        warning: "border-amber-400/20 bg-amber-400/10 text-amber-300",
        destructive: "border-rose-400/20 bg-rose-400/10 text-rose-300",
        muted: "border-white/8 bg-white/5 text-slate-400",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Badge({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof variants>) {
  return <span className={cn(variants({ variant }), className)} {...props} />;
}
