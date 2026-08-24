import {
  CalendarCheck,
  Camera,
  Fingerprint,
  ScanFace,
  Users,
  UserRoundCheck,
} from "lucide-react";

import { EnrollmentDialog } from "@/components/enrollment-dialog";
import { LiveVideo } from "@/components/live-video";
import { PageHeader } from "@/components/layout";
import { StatCard } from "@/components/stat-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import type { DashboardPayload, PresentationPayload } from "@/types";

export function DashboardPage() {
  const { data, error } = useApi<DashboardPayload>("/api/dashboard", 5000);
  const presentation = useApi<PresentationPayload>("/api/presentation", 1200);
  const stats = data?.statistics;
  return (
    <>
      <PageHeader
        eyebrow="Centro de operación"
        title="Visión general"
        description="Monitoreo en tiempo real del reconocimiento, asistencia y estado del appliance."
      />
      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard
          label="Personas"
          value={data?.people_summary.registered_people ?? "—"}
          detail="Registros civiles"
          icon={Users}
        />
        <StatCard
          label="Con biometría"
          value={data?.people_summary.biometric_identities ?? "—"}
          detail="Identidades faciales"
          icon={Fingerprint}
          tone="violet"
        />
        <StatCard
          label="Presentes"
          value={stats?.people_present ?? "—"}
          detail="Asistencia actual"
          icon={UserRoundCheck}
          tone="emerald"
        />
        <StatCard
          label="Reconocimientos"
          value={stats?.recognitions_today ?? "—"}
          detail="Confirmados hoy"
          icon={ScanFace}
        />
        <StatCard
          label="Entradas"
          value={stats?.check_ins_today ?? "—"}
          detail="Check-ins de hoy"
          icon={CalendarCheck}
          tone="emerald"
        />
        <StatCard
          label="Sin rostro"
          value={data?.people_summary.without_face ?? "—"}
          detail="Pendientes"
          icon={Camera}
          tone="amber"
        />
      </div>
      {error && (
        <div className="mb-4 rounded-xl border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-300">
          {error}
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(360px,.9fr)]">
        <LiveVideo
          cameraName={data?.camera_name}
          cameraType={data?.camera_type}
        />
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm">Estado operativo</CardTitle>
            <Badge variant={data?.available ? "success" : "warning"}>
              {data?.available ? "Disponible" : "Iniciando"}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              ["Cámara", data?.camera],
              ["Reconocimiento", data?.recognition],
              ["Base de datos", data?.database],
              ["Asistencia", data?.attendance],
            ].map(([label, value]) => (
              <div
                key={label}
                className="flex items-center justify-between rounded-xl border border-white/6 bg-white/[0.025] px-3 py-3"
              >
                <span className="text-sm text-slate-400">{label}</span>
                <span className="max-w-[60%] text-right text-xs font-semibold text-slate-200">
                  {value ?? "N/D"}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <div className="mt-5 grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
        <DataTable
          title="Reconocimientos recientes"
          headers={["Persona", "Hora", "Similitud", "Estado"]}
          rows={(data?.recent_recognitions ?? []).map((item) => [
            <PersonCell
              key={item.name + item.time}
              photo={item.photo}
              name={item.name}
            />,
            item.time,
            item.similarity == null
              ? "N/D"
              : `${(item.similarity * 100).toFixed(1)}%`,
            <Badge
              key={item.state}
              variant={item.state === "IDENTIFICADO" ? "success" : "muted"}
            >
              {item.state}
            </Badge>,
          ])}
        />
        <DataTable
          title="Asistencia de hoy"
          headers={["Persona", "Entrada", "Salida", "Estado"]}
          rows={(data?.recent_attendance ?? []).map((item) => [
            <PersonCell
              key={item.name + item.check_in}
              photo={item.photo}
              name={item.name}
            />,
            item.check_in ?? "—",
            item.check_out ?? "—",
            <Badge key={item.status} variant="success">
              {item.status}
            </Badge>,
          ])}
        />
      </div>
      <EnrollmentDialog
        presentation={presentation.data}
        refreshPresentation={presentation.refresh}
      />
    </>
  );
}

function PersonCell({ photo, name }: { photo: string | null; name: string }) {
  return (
    <div className="flex items-center gap-3">
      {photo ? (
        <img src={photo} className="size-9 rounded-lg object-cover" alt="" />
      ) : (
        <div className="grid size-9 place-items-center rounded-lg bg-white/5 text-slate-500">
          <Users className="size-4" />
        </div>
      )}
      <span className="font-medium text-slate-200">{name}</span>
    </div>
  );
}

function DataTable({
  title,
  headers,
  rows,
}: {
  title: string;
  headers: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                {headers.map((item) => (
                  <TableHead key={item}>{item}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, index) => (
                <TableRow key={index}>
                  {row.map((cell, position) => (
                    <TableCell key={position}>{cell}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="grid h-40 place-items-center rounded-xl border border-dashed border-white/8 text-sm text-slate-500">
            Sin actividad reciente
          </div>
        )}
      </CardContent>
    </Card>
  );
}
