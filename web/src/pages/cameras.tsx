import {
  Camera,
  CircleCheck,
  Plus,
  Radio,
  Star,
  TestTubeDiagonal,
  Trash2,
} from "lucide-react";
import { type FormEvent, useState } from "react";

import { PageHeader } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useApi } from "@/hooks/use-api";
import { command } from "@/lib/api";
import type { CameraDTO } from "@/types";

export function CamerasPage() {
  const { data, error, refresh } = useApi<{ cameras: CameraDTO[] }>(
    "/api/cameras",
    8000,
  );
  const [message, setMessage] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const mutate = async (
    path: string,
    payload: Record<string, unknown>,
    success: string,
  ) => {
    try {
      setMessage("Procesando…");
      await command(path, payload);
      setMessage(success);
      await refresh();
    } catch (reason) {
      setMessage(
        reason instanceof Error ? reason.message : "Operación no disponible",
      );
    }
  };
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    await mutate(
      "/api/camera/network",
      payload,
      "Cámara agregada correctamente.",
    );
    setOpen(false);
  };
  return (
    <>
      <PageHeader
        eyebrow="Fuentes de video"
        title="Administración de cámaras"
        description="Conecte cámaras locales, RTSP, HTTP/MJPEG o fuentes personalizadas sin detener el runtime."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus />
                Agregar cámara
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Nueva cámara de red</DialogTitle>
                <DialogDescription>
                  Ingrese una URL accesible desde este appliance.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={submit} className="space-y-4">
                <label className="block text-sm text-slate-300">
                  Nombre
                  <Input
                    name="name"
                    className="mt-2"
                    placeholder="Entrada principal"
                    required
                  />
                </label>
                <label className="block text-sm text-slate-300">
                  Tipo
                  <select
                    name="type"
                    defaultValue="NETWORK_RTSP"
                    className="mt-2 h-10 w-full rounded-lg border border-white/10 bg-slate-950/55 px-3 text-sm text-white"
                  >
                    <option value="NETWORK_RTSP">RTSP / RTSPS</option>
                    <option value="NETWORK_HTTP">HTTP / MJPEG</option>
                    <option value="CUSTOM">URL personalizada</option>
                  </select>
                </label>
                <label className="block text-sm text-slate-300">
                  URL
                  <Input
                    name="url"
                    className="mt-2"
                    placeholder="rtsp://usuario:contraseña@192.168.1.50:554/stream1"
                    required
                  />
                </label>
                <div className="rounded-xl border border-cyan-400/15 bg-cyan-400/5 p-3 text-xs leading-relaxed text-slate-400">
                  <strong className="text-cyan-200">
                    Cómo encontrar la URL:
                  </strong>{" "}
                  consulte la configuración ONVIF del fabricante. Ejemplos
                  comunes: Hikvision <code>/Streaming/Channels/101</code>, Dahua{" "}
                  <code>/cam/realmonitor?channel=1&amp;subtype=0</code>, Reolink{" "}
                  <code>/h264Preview_01_main</code> y Axis{" "}
                  <code>/axis-media/media.amp</code>.
                </div>
                <div className="flex justify-end gap-2">
                  <Button type="submit">Guardar cámara</Button>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setOpen(false)}
                  >
                    Cancelar
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        }
      />
      {(message || error) && (
        <div className="mb-5 rounded-xl border border-cyan-400/15 bg-cyan-400/5 px-4 py-3 text-sm text-cyan-100">
          {message || error}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
        {(data?.cameras ?? []).map((camera) => (
          <Card
            key={camera.id}
            className={
              camera.active ? "border-cyan-400/25 shadow-cyan-950/30" : ""
            }
          >
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div className="flex gap-3">
                <div
                  className={`grid size-11 place-items-center rounded-xl ${camera.active ? "bg-cyan-400/12 text-cyan-300" : "bg-white/5 text-slate-500"}`}
                >
                  <Camera />
                </div>
                <div>
                  <CardTitle>{camera.name}</CardTitle>
                  <CardDescription className="mt-1">
                    {camera.type}
                  </CardDescription>
                </div>
              </div>
              <Badge
                variant={
                  camera.active
                    ? "success"
                    : camera.available
                      ? "default"
                      : "muted"
                }
              >
                {camera.status}
              </Badge>
            </CardHeader>
            <CardContent>
              <div className="mb-4 flex items-center gap-4 text-xs text-slate-500">
                <span className="flex items-center gap-1.5">
                  <Radio className="size-3.5" />
                  {camera.network ? "Red" : "Local"}
                </span>
                {camera.preferred && (
                  <span className="flex items-center gap-1.5 text-amber-300">
                    <Star className="size-3.5 fill-current" />
                    Principal
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  size="sm"
                  onClick={() =>
                    mutate(
                      "/api/camera/connect",
                      { source_id: camera.id },
                      "Cámara conectada.",
                    )
                  }
                >
                  <CircleCheck />
                  Usar
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    mutate(
                      "/api/camera/probe",
                      { source_id: camera.id },
                      "Prueba completada.",
                    )
                  }
                >
                  <TestTubeDiagonal />
                  Probar
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() =>
                    mutate(
                      "/api/camera/preferred",
                      { source_id: camera.id },
                      "Cámara principal actualizada.",
                    )
                  }
                >
                  <Star />
                  Principal
                </Button>
                {camera.network && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-rose-300"
                    onClick={() => {
                      if (window.confirm(`¿Eliminar ${camera.name}?`))
                        void mutate(
                          "/api/camera/network/delete",
                          { source_id: camera.id, confirmed: true },
                          "Cámara eliminada.",
                        );
                    }}
                  >
                    <Trash2 />
                    Eliminar
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      {!data?.cameras.length && (
        <Card>
          <CardContent className="grid min-h-64 place-items-center text-center">
            <div>
              <Camera className="mx-auto size-10 text-slate-600" />
              <h3 className="mt-4 font-semibold text-slate-200">
                No hay cámaras disponibles
              </h3>
              <p className="mt-1 text-sm text-slate-500">
                Agregue una cámara IP o conecte un dispositivo local.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
    </>
  );
}
