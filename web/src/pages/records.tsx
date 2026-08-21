import {
  Activity,
  ArchiveRestore,
  CalendarCheck,
  ClipboardList,
  FileChartColumn,
  History,
  RefreshCw,
  Settings,
} from "lucide-react";

import { PageHeader } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

export function AttendancePage() {
  return (
    <CollectionPage
      endpoint="/api/attendance"
      keyName="attendance"
      eyebrow="Control horario"
      title="Asistencia"
      description="Entradas, salidas y estado del día."
      icon={CalendarCheck}
      columns={["name", "date", "check_in", "check_out", "status"]}
    />
  );
}
export function HistoryPage() {
  return (
    <CollectionPage
      endpoint="/api/history"
      keyName="events"
      eyebrow="Trazabilidad"
      title="Historial de detecciones"
      description="Actividad reciente del pipeline de reconocimiento."
      icon={History}
      columns={["name", "time", "type", "similarity", "camera"]}
    />
  );
}
export function AuditPage() {
  return (
    <CollectionPage
      endpoint="/api/audit"
      keyName="events"
      eyebrow="Gobernanza"
      title="Auditoría"
      description="Eventos administrativos y de seguridad registrados por los casos de uso."
      icon={ClipboardList}
      columns={[
        "timestamp_utc",
        "action",
        "entity_type",
        "actor_role",
        "success",
        "message",
      ]}
    />
  );
}
export function BackupsPage() {
  return (
    <CollectionPage
      endpoint="/api/backups"
      keyName="operations"
      eyebrow="Continuidad"
      title="Copias de seguridad"
      description="Operaciones recientes de backup, verificación y restauración."
      icon={ArchiveRestore}
      columns={["operation", "status", "started_at", "finished_at", "message"]}
    />
  );
}

export function ReportsPage() {
  return (
    <ObjectPage
      endpoint="/api/reports"
      eyebrow="Analítica"
      title="Reportes"
      description="Resumen diario generado desde los casos de uso de reportes."
      icon={FileChartColumn}
    />
  );
}
export function DiagnosticsPage() {
  return (
    <ObjectPage
      endpoint="/api/diagnostics"
      eyebrow="Observabilidad"
      title="Diagnóstico del sistema"
      description="Estado consolidado de runtime, cámara, bases de datos y workers."
      icon={Activity}
    />
  );
}
export function SettingsPage() {
  return (
    <ObjectPage
      endpoint="/api/settings"
      eyebrow="Administración"
      title="Configuración"
      description="Proyección segura y redactada de la configuración activa."
      icon={Settings}
    />
  );
}

function CollectionPage({
  endpoint,
  keyName,
  eyebrow,
  title,
  description,
  icon: Icon,
  columns,
}: {
  endpoint: string;
  keyName: string;
  eyebrow: string;
  title: string;
  description: string;
  icon: typeof CalendarCheck;
  columns: string[];
}) {
  const { data, error, refresh } = useApi<Record<string, unknown>>(
    endpoint,
    15000,
  );
  const rows = Array.isArray(data?.[keyName])
    ? (data[keyName] as Array<Record<string, unknown>>)
    : [];
  return (
    <>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actions={
          <Button variant="secondary" onClick={() => void refresh()}>
            <RefreshCw />
            Actualizar
          </Button>
        }
      />
      {error && (
        <div className="mb-4 rounded-xl border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-300">
          {error}
        </div>
      )}
      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300">
              <Icon />
            </div>
            <CardTitle>{title}</CardTitle>
          </div>
          <Badge variant="muted">{rows.length} registros</Badge>
        </CardHeader>
        <CardContent>
          {rows.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  {columns.map((column) => (
                    <TableHead key={column}>{label(column)}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, index) => (
                  <TableRow key={index}>
                    {columns.map((column) => (
                      <TableCell key={column}>{format(row[column])}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <Empty />
          )}
        </CardContent>
      </Card>
    </>
  );
}

function ObjectPage({
  endpoint,
  eyebrow,
  title,
  description,
  icon: Icon,
}: {
  endpoint: string;
  eyebrow: string;
  title: string;
  description: string;
  icon: typeof Activity;
}) {
  const { data, error, refresh } = useApi<Record<string, unknown>>(
    endpoint,
    15000,
  );
  return (
    <>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actions={
          <Button variant="secondary" onClick={() => void refresh()}>
            <RefreshCw />
            Actualizar
          </Button>
        }
      />
      {error && (
        <div className="mb-4 rounded-xl border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-300">
          {error}
        </div>
      )}
      <Card>
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <div className="grid size-10 place-items-center rounded-xl bg-cyan-400/10 text-cyan-300">
            <Icon />
          </div>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent>
          {data ? <ObjectGrid value={data} /> : <Empty />}
        </CardContent>
      </Card>
    </>
  );
}

function ObjectGrid({ value }: { value: Record<string, unknown> }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {Object.entries(value).map(([key, item]) => (
        <div
          key={key}
          className="rounded-xl border border-white/6 bg-white/[0.025] p-4"
        >
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            {label(key)}
          </div>
          {item && typeof item === "object" ? (
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs leading-relaxed text-slate-300">
              {JSON.stringify(item, null, 2)}
            </pre>
          ) : (
            <div className="text-sm text-slate-200">{format(item)}</div>
          )}
        </div>
      ))}
    </div>
  );
}
function Empty() {
  return (
    <div className="grid min-h-60 place-items-center text-sm text-slate-500">
      No hay información disponible.
    </div>
  );
}
function label(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function format(value: unknown) {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Sí" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
