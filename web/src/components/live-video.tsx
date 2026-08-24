import { CameraOff, Maximize2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function LiveVideo({
  cameraName,
  cameraType,
}: {
  cameraName?: string;
  cameraType?: string;
}) {
  const [failed, setFailed] = useState(false);
  const [key, setKey] = useState(0);
  const reload = () => {
    setFailed(false);
    setKey((value) => value + 1);
  };
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-white/6 py-4">
        <div>
          <CardTitle className="text-sm">Video en tiempo real</CardTitle>
          <p className="mt-1 text-xs text-slate-500">
            {cameraName ?? "Sin cámara"} · {cameraType ?? "N/D"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={failed ? "destructive" : "success"}>
            <span className="size-1.5 rounded-full bg-current" />
            {failed ? "Sin señal" : "En vivo"}
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            onClick={reload}
            aria-label="Recargar video"
          >
            <Maximize2 />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="relative aspect-video bg-[#02060c] p-0">
        {failed ? (
          <div className="absolute inset-0 grid place-items-center">
            <div className="text-center text-slate-500">
              <CameraOff className="mx-auto mb-3 size-9" />
              <p className="text-sm">Esperando una señal de video</p>
              <Button variant="secondary" size="sm" onClick={reload}>
                Reintentar
              </Button>
            </div>
          </div>
        ) : (
          <img
            key={key}
            src="/api/video.mjpeg"
            className="size-full object-contain"
            alt="Video en vivo"
            onError={() => setFailed(true)}
          />
        )}
        <div className="ambient-line absolute inset-x-0 top-0 h-px" />
      </CardContent>
    </Card>
  );
}
