import {
  Activity,
  ArchiveRestore,
  CalendarCheck,
  Camera,
  ChartNoAxesCombined,
  ClipboardList,
  Fingerprint,
  Gauge,
  History,
  Menu,
  Settings,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const navigation = [
  ["/", "Operación", Gauge],
  ["/camera", "Cámaras", Camera],
  ["/people", "Personas", Users],
  ["/attendance", "Asistencia", CalendarCheck],
  ["/history", "Historial", History],
  ["/reports", "Reportes", ChartNoAxesCombined],
  ["/backups", "Backups", ArchiveRestore],
  ["/audit", "Auditoría", ClipboardList],
  ["/diagnostics", "Diagnóstico", Activity],
  ["/settings", "Configuración", Settings],
] as const;

export function Layout({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const path = window.location.pathname;

  return (
    <div className="dot-grid min-h-screen lg:grid lg:grid-cols-[250px_1fr]">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-[250px] -translate-x-full flex-col border-r border-white/8 bg-[#07101d]/95 p-4 backdrop-blur-xl transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0",
          open && "translate-x-0",
        )}
      >
        <div className="mb-7 flex items-center gap-3 px-2 pt-2">
          <div className="grid size-11 place-items-center rounded-xl border border-cyan-400/25 bg-cyan-400/10 shadow-lg shadow-cyan-500/10">
            <Fingerprint className="size-6 text-cyan-300" />
          </div>
          <div>
            <div className="font-semibold tracking-[.14em] text-white">
              FASTVISION
            </div>
            <div className="text-[10px] font-semibold tracking-[.2em] text-cyan-300/70">
              CONTROL CENTER
            </div>
          </div>
          <Button
            className="ml-auto lg:hidden"
            variant="ghost"
            size="icon"
            onClick={() => setOpen(false)}
            aria-label="Cerrar menú"
          >
            <X />
          </Button>
        </div>

        <nav className="space-y-1">
          {navigation.map(([href, label, Icon]) => {
            const selected =
              href === "/" ? path === href : path.startsWith(href);
            return (
              <a
                key={href}
                href={href}
                className={cn(
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-400 transition hover:bg-white/5 hover:text-white",
                  selected &&
                    "border border-cyan-400/15 bg-cyan-400/10 text-cyan-100 shadow-sm shadow-cyan-900/20",
                )}
              >
                <Icon
                  className={cn(
                    "size-[18px] text-slate-500 group-hover:text-cyan-300",
                    selected && "text-cyan-300",
                  )}
                />
                {label}
                {selected && (
                  <span className="ml-auto size-1.5 rounded-full bg-cyan-300 shadow-[0_0_10px_#67e8f9]" />
                )}
              </a>
            );
          })}
        </nav>

        <div className="mt-auto rounded-2xl border border-white/8 bg-white/[0.035] p-3.5">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-200">
            <ShieldCheck className="size-4 text-emerald-300" /> Appliance
            protegido
          </div>
          <p className="m-0 text-[11px] leading-relaxed text-slate-500">
            Acceso permitido únicamente desde localhost o una LAN privada
            confiable.
          </p>
        </div>
      </aside>

      {open && (
        <button
          className="fixed inset-0 z-30 bg-slate-950/75 lg:hidden"
          onClick={() => setOpen(false)}
          aria-label="Cerrar navegación"
        />
      )}

      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-white/8 bg-[#050b14]/80 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setOpen(true)}
            aria-label="Abrir menú"
          >
            <Menu />
          </Button>
          <div className="hidden items-center gap-2 text-sm text-slate-400 sm:flex">
            <Activity className="size-4 text-cyan-300" /> Sistema de visión
            local
          </div>
          <div className="ml-auto flex items-center gap-3">
            <Badge variant="success">
              <span className="pulse-soft size-1.5 rounded-full bg-emerald-300" />{" "}
              Runtime activo
            </Badge>
            <div className="hidden h-7 w-px bg-white/8 sm:block" />
            <div className="hidden text-right sm:block">
              <div className="text-xs font-semibold text-slate-200">
                Modo appliance
              </div>
              <div className="text-[10px] text-slate-500">Red local</div>
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div className="mb-2 text-[11px] font-bold uppercase tracking-[.2em] text-cyan-400">
          {eyebrow}
        </div>
        <h1 className="m-0 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          {title}
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">{description}</p>
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
