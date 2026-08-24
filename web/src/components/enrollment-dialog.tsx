import { Camera, CheckCircle2, Fingerprint, UserRoundPlus } from "lucide-react";
import { type FormEvent, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { command } from "@/lib/api";
import { useApi } from "@/hooks/use-api";
import type { EnrollmentStatus, PresentationPayload } from "@/types";

export function EnrollmentDialog({
  presentation,
  refreshPresentation,
}: {
  presentation: PresentationPayload | null;
  refreshPresentation: () => Promise<void>;
}) {
  const { data: enrollment, refresh } = useApi<EnrollmentStatus>(
    "/api/enrollment/status",
    1000,
  );
  const [error, setError] = useState<string | null>(null);
  const active = Boolean(presentation?.active || enrollment?.active);

  const run = async (path: string, payload: Record<string, unknown> = {}) => {
    try {
      setError(null);
      await command(path, payload);
      await Promise.all([refresh(), refreshPresentation()]);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Operación no disponible",
      );
    }
  };

  const cancel = () => run("/api/enrollment/cancel");
  const ignore = () => run("/api/presentation/ignore");

  return (
    <Dialog
      open={active}
      onOpenChange={(value) => {
        if (!value) void (enrollment?.active ? cancel() : ignore());
      }}
    >
      <DialogContent className="max-w-2xl">
        {enrollment?.active ? (
          <EnrollmentContent status={enrollment} run={run} error={error} />
        ) : (
          <PresentationContent
            value={presentation}
            start={() => run("/api/enrollment/start")}
            ignore={ignore}
            error={error}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function PresentationContent({
  value,
  start,
  ignore,
  error,
}: {
  value: PresentationPayload | null;
  start: () => void;
  ignore: () => void;
  error: string | null;
}) {
  if (!value) return null;
  return (
    <>
      <DialogHeader>
        <div className="mb-3 grid size-11 place-items-center rounded-xl border border-cyan-400/20 bg-cyan-400/10">
          <Fingerprint className="size-6 text-cyan-300" />
        </div>
        <DialogTitle>{value.title}</DialogTitle>
        <DialogDescription>{value.status}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-5 sm:grid-cols-[150px_1fr]">
        {value.photo ? (
          <img
            src={value.photo}
            className="aspect-square w-full rounded-xl border border-white/10 object-cover"
            alt="Persona detectada"
          />
        ) : (
          <div className="grid aspect-square place-items-center rounded-xl border border-dashed border-white/10 bg-white/[0.025] text-slate-600">
            <Fingerprint className="size-10" />
          </div>
        )}
        <div>
          {value.name && (
            <h3 className="mb-3 text-lg font-semibold text-white">
              {value.name}
            </h3>
          )}
          <div className="space-y-2">
            {value.details?.map((item) => (
              <div
                key={item.label}
                className="flex justify-between gap-4 border-b border-white/6 pb-2 text-sm"
              >
                <span className="text-slate-500">{item.label}</span>
                <span className="text-right text-slate-200">{item.value}</span>
              </div>
            ))}
          </div>
          {value.similarity != null && (
            <p className="mt-3 text-sm text-slate-400">
              Similitud{" "}
              <strong className="text-cyan-300">
                {(value.similarity * 100).toFixed(1)}%
              </strong>
            </p>
          )}
          {value.warning && (
            <p className="mt-3 text-sm text-amber-300">{value.warning}</p>
          )}
        </div>
      </div>
      {error && <p className="mt-4 text-sm text-rose-300">{error}</p>}
      <div className="mt-6 flex justify-end gap-2">
        {value.kind === "UNKNOWN" && (
          <Button onClick={start}>
            <UserRoundPlus />
            Registrar persona
          </Button>
        )}
        <Button variant="secondary" onClick={ignore}>
          Ignorar
        </Button>
      </div>
    </>
  );
}

function EnrollmentContent({
  status,
  run,
  error,
}: {
  status: EnrollmentStatus;
  run: (path: string, payload?: Record<string, unknown>) => Promise<void>;
  error: string | null;
}) {
  const submitPerson = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    void run("/api/enrollment/person", {
      ...values,
      consent_confirmed: values.consent_confirmed === "on",
    });
  };
  return (
    <>
      <DialogHeader>
        <div className="flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300">
            <UserRoundPlus />
          </div>
          <div>
            <DialogTitle>Registro de persona</DialogTitle>
            <DialogDescription>
              Flujo seguro de datos civiles y biometría facial
            </DialogDescription>
          </div>
        </div>
      </DialogHeader>
      <div className="mb-5 flex items-center gap-2">
        {["PERSON", "PREPARATION", "CAPTURE", "PHOTO", "CONFIRMATION"].map(
          (stage, index) => (
            <div
              key={stage}
              className={`h-1.5 flex-1 rounded-full ${index <= stageIndex(status.stage) ? "bg-cyan-400" : "bg-white/8"}`}
            />
          ),
        )}
      </div>
      {status.stage === "PERSON" && (
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={submitPerson}>
          <Input name="first_name" placeholder="Nombre" required />
          <Input name="last_name" placeholder="Apellido" required />
          <Input name="cedula" placeholder="Cédula" required />
          <Input name="position" placeholder="Cargo" />
          <Input name="department" placeholder="Departamento" />
          <Input name="company" placeholder="Empresa" />
          <Input name="phone" placeholder="Teléfono" />
          <Input name="email" type="email" placeholder="Correo" />
          <Input
            name="address"
            className="sm:col-span-2"
            placeholder="Dirección"
          />
          <label className="flex items-center gap-2 text-sm text-slate-300 sm:col-span-2">
            <input
              name="consent_confirmed"
              type="checkbox"
              required
              className="accent-cyan-400"
            />
            Consentimiento biométrico confirmado
          </label>
          <div className="flex justify-end gap-2 sm:col-span-2">
            <Button type="submit">Continuar</Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => run("/api/enrollment/cancel")}
            >
              Cancelar
            </Button>
          </div>
        </form>
      )}
      {status.stage === "PREPARATION" && (
        <div className="space-y-5">
          <div className="rounded-xl border border-white/8 bg-white/[0.025] p-4 text-sm text-slate-300">
            <h3 className="mb-3 font-semibold text-white">Antes de capturar</h3>
            <ul className="grid gap-2 sm:grid-cols-2">
              <li>• Mire directamente a la cámara</li>
              <li>• Mantenga buena iluminación</li>
              <li>• Rostro completamente visible</li>
              <li>• Evite movimientos bruscos</li>
            </ul>
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => run("/api/enrollment/capture/start")}>
              <Camera />
              Iniciar captura
            </Button>
            <Button
              variant="secondary"
              onClick={() => run("/api/enrollment/cancel")}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}
      {["CAPTURE", "VALIDATION"].includes(status.stage) && (
        <div className="space-y-4">
          <div className="overflow-hidden rounded-xl border border-white/8 bg-black">
            <img
              src="/api/video.mjpeg"
              className="aspect-video w-full object-contain"
              alt="Captura facial"
            />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-white">
                {status.instruction ?? "Mire al frente"}
              </div>
              <div className="mt-1 text-xs text-slate-500">
                Calidad: {status.quality_score?.toFixed(1) ?? "N/D"} ·{" "}
                {status.quality_band ?? "N/D"}
              </div>
            </div>
            <Badge variant="default">
              {status.accepted_samples} / {status.target_samples} muestras
            </Badge>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/8">
            <div
              className="h-full rounded-full bg-cyan-400 transition-all"
              style={{
                width: `${Math.min(100, (status.accepted_samples / Math.max(1, status.target_samples)) * 100)}%`,
              }}
            />
          </div>
          <div className="flex justify-end gap-2">
            {!status.can_continue && (
              <Button onClick={() => run("/api/enrollment/capture/start")}>
                Capturar muestra
              </Button>
            )}
            <Button
              variant="secondary"
              onClick={() => run("/api/enrollment/cancel")}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}
      {status.stage === "PHOTO" && (
        <div className="space-y-5 text-center">
          <div className="mx-auto grid size-20 place-items-center rounded-2xl border border-cyan-400/20 bg-cyan-400/10">
            <Camera className="size-9 text-cyan-300" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">
              Fotografía de perfil
            </h3>
            <p className="mt-1 text-sm text-slate-400">
              Puede agregar una fotografía o continuar sin ella.
            </p>
          </div>
          <div className="flex justify-center gap-2">
            <Button
              onClick={() => run("/api/enrollment/photo", { action: "TAKE" })}
            >
              Tomar fotografía
            </Button>
            <Button
              variant="secondary"
              onClick={() => run("/api/enrollment/photo", { action: "SKIP" })}
            >
              Omitir
            </Button>
          </div>
        </div>
      )}
      {status.stage === "PHOTO_CAPTURE" && (
        <div className="space-y-4">
          <div className="overflow-hidden rounded-xl border border-white/8 bg-black">
            <img
              src="/api/video.mjpeg"
              className="aspect-video w-full object-contain"
              alt="Fotografía de perfil"
            />
          </div>
          <div>
            <h3 className="font-semibold text-white">Prepare la fotografía</h3>
            <p className="mt-1 text-sm text-slate-400">
              Mire al frente y capture cuando el encuadre sea correcto.
            </p>
          </div>
          <div className="flex justify-end gap-2">
            <Button
              onClick={() =>
                run("/api/enrollment/photo", { action: "CAPTURE" })
              }
            >
              <Camera />
              Capturar fotografía
            </Button>
            <Button
              variant="secondary"
              onClick={() => run("/api/enrollment/cancel")}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}
      {status.stage === "PHOTO_CONFIRMATION" && (
        <div className="space-y-4">
          <div className="overflow-hidden rounded-xl border border-white/8 bg-black">
            <img
              src="/api/video.mjpeg"
              className="aspect-video w-full object-contain"
              alt="Fotografía capturada"
            />
          </div>
          <div>
            <h3 className="font-semibold text-white">Confirme la fotografía</h3>
            <p className="mt-1 text-sm text-slate-400">
              Puede usar esta captura o tomarla nuevamente.
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              onClick={() =>
                run("/api/enrollment/photo", { action: "CONFIRM" })
              }
            >
              <CheckCircle2 />
              Usar fotografía
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                run("/api/enrollment/photo", { action: "CAPTURE" })
              }
            >
              Repetir captura
            </Button>
            <Button
              variant="ghost"
              onClick={() => run("/api/enrollment/cancel")}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}
      {status.stage === "CONFIRMATION" && (
        <div className="space-y-5">
          <div className="rounded-xl border border-white/8 bg-white/[0.025] p-4">
            <h3 className="mb-3 font-semibold text-white">
              Verifique el registro
            </h3>
            {Object.entries(status.summary).map(([key, value]) => (
              <div
                key={key}
                className="flex justify-between border-b border-white/6 py-2 text-sm"
              >
                <span className="capitalize text-slate-500">
                  {key.replace("_", " ")}
                </span>
                <span className="text-slate-200">{value}</span>
              </div>
            ))}
            <div className="mt-3 text-sm text-cyan-300">
              {status.accepted_samples} muestras biométricas válidas
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => run("/api/enrollment/confirm")}>
              <CheckCircle2 />
              Confirmar registro
            </Button>
            <Button
              variant="secondary"
              onClick={() => run("/api/enrollment/cancel")}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}
      {status.stage === "COMPLETE" && (
        <div className="py-8 text-center">
          <CheckCircle2 className="mx-auto size-14 text-emerald-300" />
          <h3 className="mt-4 text-xl font-semibold text-white">
            Persona registrada correctamente
          </h3>
          <p className="mt-2 text-sm text-slate-400">
            La información civil y biométrica quedó vinculada.
          </p>
          <Button className="mt-5" onClick={() => window.location.reload()}>
            Finalizar
          </Button>
        </div>
      )}
      {error && (
        <p className="mt-4 rounded-lg border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-300">
          {error}
        </p>
      )}
    </>
  );
}

function stageIndex(stage: string) {
  if (stage === "PERSON") return 0;
  if (stage === "PREPARATION") return 1;
  if (["CAPTURE", "VALIDATION"].includes(stage)) return 2;
  if (["PHOTO", "PHOTO_CAPTURE", "PHOTO_CONFIRMATION"].includes(stage))
    return 3;
  return 4;
}
