import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function StatCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = "cyan",
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: LucideIcon;
  tone?: "cyan" | "emerald" | "amber" | "violet";
}) {
  const colors = {
    cyan: "bg-cyan-400/10 text-cyan-300 border-cyan-400/15",
    emerald: "bg-emerald-400/10 text-emerald-300 border-emerald-400/15",
    amber: "bg-amber-400/10 text-amber-300 border-amber-400/15",
    violet: "bg-violet-400/10 text-violet-300 border-violet-400/15",
  };
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              {label}
            </div>
            <div className="mt-2 text-2xl font-semibold text-white">
              {value}
            </div>
            <div className="mt-1 text-xs text-slate-500">{detail}</div>
          </div>
          <div
            className={`grid size-10 place-items-center rounded-xl border ${colors[tone]}`}
          >
            <Icon className="size-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
