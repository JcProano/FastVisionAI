import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-semibold transition-all outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-500/15 hover:bg-cyan-300",
        secondary:
          "border border-white/10 bg-white/5 text-slate-100 hover:bg-white/10",
        ghost: "text-slate-300 hover:bg-white/8 hover:text-white",
        destructive: "bg-rose-500 text-white hover:bg-rose-400",
        outline:
          "border border-cyan-400/30 bg-cyan-400/5 text-cyan-200 hover:bg-cyan-400/12",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-12 rounded-xl px-6",
        icon: "size-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({
  className,
  variant,
  size,
  asChild,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}
