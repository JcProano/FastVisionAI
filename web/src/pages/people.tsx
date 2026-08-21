import {
  Camera,
  Fingerprint,
  Search,
  Trash2,
  UserPen,
  Users,
} from "lucide-react";
import { type FormEvent, useState } from "react";

import { PageHeader } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useApi } from "@/hooks/use-api";
import { command } from "@/lib/api";
import type { PersonDTO } from "@/types";

export function PeoplePage() {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const { data, error, refresh } = useApi<{
    people: PersonDTO[];
    total: number;
  }>(`/api/people${search ? `?q=${encodeURIComponent(search)}` : ""}`, 10000);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSearch(query.trim());
  };
  const mutate = async (
    path: string,
    payload: Record<string, unknown>,
    success: string,
  ) => {
    try {
      await command(path, payload);
      setMessage(success);
      await refresh();
    } catch (reason) {
      setMessage(
        reason instanceof Error ? reason.message : "Operación no disponible",
      );
    }
  };
  const edit = async (person: PersonDTO) => {
    const first_name = window.prompt("Nombre", person.first_name);
    if (first_name == null) return;
    const last_name = window.prompt("Apellido", person.last_name);
    if (last_name == null) return;
    const phone = window.prompt("Teléfono", person.phone ?? "");
    if (phone == null) return;
    const email = window.prompt("Correo", person.email ?? "");
    if (email == null) return;
    await mutate(
      "/api/person/update",
      {
        token: person.token,
        first_name,
        last_name,
        phone,
        email,
        status: person.status,
      },
      "Persona actualizada.",
    );
  };
  const remove = async (person: PersonDTO) => {
    if (
      !window.confirm(
        `Eliminar a ${person.name}\n\nEl historial se conservará.`,
      )
    )
      return;
    if (window.prompt("Escriba ELIMINAR para confirmar") !== "ELIMINAR") return;
    await mutate(
      "/api/person/delete",
      { token: person.token, confirmed: true, confirmation: "ELIMINAR" },
      "Persona eliminada.",
    );
  };
  return (
    <>
      <PageHeader
        eyebrow="Base civil"
        title="Personas"
        description="Consulte y administre registros civiles, fotografías y enrolamientos biométricos."
        actions={
          <Button asChild>
            <a href="/">
              <Fingerprint />
              Registrar persona
            </a>
          </Button>
        }
      />
      <Card className="mb-5">
        <CardContent className="p-4">
          <form onSubmit={submit} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="pl-9"
                placeholder="Buscar por nombre, cédula o correo"
              />
            </div>
            <Button type="submit" variant="secondary">
              Buscar
            </Button>
          </form>
        </CardContent>
      </Card>
      {(message || error) && (
        <div className="mb-4 rounded-xl border border-white/8 bg-white/[0.035] p-3 text-sm text-slate-300">
          {message || error}
        </div>
      )}
      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between border-b border-white/8 px-5 py-4">
            <div>
              <h3 className="font-semibold text-white">Registros</h3>
              <p className="mt-1 text-xs text-slate-500">
                {data?.total ?? 0} personas encontradas
              </p>
            </div>
            <Badge variant="muted">SQLite</Badge>
          </div>
          {data?.people.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Persona</TableHead>
                  <TableHead>Cédula</TableHead>
                  <TableHead>Contacto</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Biometría</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.people.map((person) => (
                  <TableRow key={person.token}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        {person.thumbnail ? (
                          <img
                            src={person.thumbnail}
                            className="size-10 rounded-xl object-cover"
                            alt=""
                          />
                        ) : (
                          <div className="grid size-10 place-items-center rounded-xl bg-white/5 text-slate-500">
                            <Users className="size-4" />
                          </div>
                        )}
                        <div>
                          <div className="font-medium text-slate-100">
                            {person.name}
                          </div>
                          <div className="text-xs text-slate-500">
                            {person.email || "Sin correo"}
                          </div>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>{person.cedula}</TableCell>
                    <TableCell>
                      <div>{person.phone || "—"}</div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          person.status === "ACTIVE" ? "success" : "muted"
                        }
                      >
                        {person.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="flex items-center gap-2 text-xs">
                        <Fingerprint className="size-4 text-cyan-300" />
                        {person.biometrics}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Editar"
                          onClick={() => void edit(person)}
                        >
                          <UserPen />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Actualizar fotografía"
                          onClick={() =>
                            void mutate(
                              "/api/person/photo",
                              { token: person.token, confirmed: true },
                              "Captura de fotografía iniciada.",
                            )
                          }
                        >
                          <Camera />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          title="Actualizar rostro"
                          onClick={() =>
                            void mutate(
                              "/api/person/face",
                              { token: person.token, confirmed: true },
                              "Enrolamiento facial iniciado.",
                            )
                          }
                        >
                          <Fingerprint />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-rose-300"
                          title="Eliminar"
                          onClick={() => void remove(person)}
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="grid min-h-64 place-items-center text-center">
              <div>
                <Users className="mx-auto size-10 text-slate-600" />
                <p className="mt-3 text-sm text-slate-500">
                  No se encontraron personas
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
