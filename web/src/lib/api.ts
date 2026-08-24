let csrfRequest: Promise<string> | null = null;

async function csrfToken(): Promise<string> {
  if (!csrfRequest) {
    csrfRequest = fetch("/api/session", {
      credentials: "same-origin",
      cache: "no-store",
    })
      .then(readJson)
      .then((value) => String(value.csrf_token))
      .catch((error) => {
        csrfRequest = null;
        throw error;
      });
  }
  return csrfRequest;
}

export async function api<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
  });
  return readJson(response) as Promise<T>;
}

export async function command<T = unknown>(
  path: string,
  body: Record<string, unknown> = {},
): Promise<T> {
  const token = await csrfToken();
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": token,
    },
    body: JSON.stringify(body),
  });
  if (response.status === 403) csrfRequest = null;
  return readJson(response) as Promise<T>;
}

async function readJson(response: Response): Promise<Record<string, unknown>> {
  const value = (await response.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;
  if (!response.ok) {
    throw new Error(
      String(value.error ?? value.detail ?? "Operación no disponible"),
    );
  }
  return value;
}
