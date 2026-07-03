/**
 * client.ts — Cliente HTTP mínimo sobre fetch.
 *
 * La sesión viaja en una cookie httpOnly (mismo origen vía nginx),
 * así que no hay tokens que manejar aquí.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    detail: string,
    public sugerencia?: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `Error ${res.status}`;
  let sugerencia: string | undefined;
  try {
    const data = (await res.json()) as { detail?: string; sugerencia?: string };
    if (data.detail) detail = data.detail;
    sugerencia = data.sugerencia;
  } catch {
    /* respuesta sin JSON: se queda el mensaje genérico */
  }
  return new ApiError(res.status, detail, sugerencia);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

async function conCuerpo<T>(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

export const apiPost = <T,>(path: string, body?: unknown) =>
  conCuerpo<T>("POST", path, body);
export const apiPut = <T,>(path: string, body?: unknown) =>
  conCuerpo<T>("PUT", path, body);
export const apiDelete = <T,>(path: string, body?: unknown) =>
  conCuerpo<T>("DELETE", path, body);
