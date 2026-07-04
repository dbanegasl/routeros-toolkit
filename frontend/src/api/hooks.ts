/**
 * hooks.ts — Hooks de datos (TanStack Query) sobre la API.
 *
 * Toda petición 401 marca la sesión como cerrada (el Layout redirige
 * al login sin recargar la página).
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiDelete, apiGet, apiPost, apiPut, ApiError } from "./client";
import type {
  BloqueosResp,
  Config,
  Consumo,
  DispositivosResp,
  Horario,
  QosDiagnostico,
  QosPlan,
  RespaldoCreado,
  RespaldosResp,
  Sesion,
  Sistema,
  Validacion,
  WhitelistResp,
} from "./types";

/** Reintenta errores de red, pero nunca un 401/4xx. */
function reintentar(fallos: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return fallos < 2;
}

export function useSesion() {
  return useQuery<Sesion>({
    queryKey: ["sesion"],
    queryFn: () => apiGet<Sesion>("/api/auth/sesion"),
    staleTime: 60_000,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (password: string) =>
      apiPost<{ mensaje: string }>("/api/auth/login", { password }),
    onSuccess: () => {
      qc.setQueryData<Sesion>(["sesion"], { autenticada: true });
      void qc.invalidateQueries();
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost<{ mensaje: string }>("/api/auth/logout"),
    onSuccess: () => {
      qc.setQueryData<Sesion>(["sesion"], { autenticada: false });
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "sesion" });
    },
  });
}

/** Opciones comunes de las lecturas del router. */
function lectura<T>(key: string, path: string, refetchMs?: number) {
  return {
    queryKey: [key],
    queryFn: () => apiGet<T>(path),
    retry: reintentar,
    refetchInterval: refetchMs,
  };
}

export const useSistema = () =>
  useQuery<Sistema>(lectura<Sistema>("sistema", "/api/sistema", 15_000));

export const useDispositivos = () =>
  useQuery<DispositivosResp>(
    lectura<DispositivosResp>("dispositivos", "/api/dispositivos", 60_000),
  );

export const useHorario = () =>
  useQuery<Horario>(lectura<Horario>("horario", "/api/horario", 60_000));

export const useValidacion = () =>
  useQuery<Validacion>(lectura<Validacion>("validacion", "/api/validacion"));

export const useConfig = () =>
  useQuery<Config>(lectura<Config>("config", "/api/config"));

export const useConsumo = (top = 5) =>
  useQuery<Consumo>(
    lectura<Consumo>("consumo", `/api/consumo?top=${top}`, 15_000),
  );

export const useBloqueos = () =>
  useQuery<BloqueosResp>(
    lectura<BloqueosResp>("bloqueos", "/api/bloqueos", 60_000),
  );

export const useWhitelist = () =>
  useQuery<WhitelistResp>(
    lectura<WhitelistResp>("whitelist", "/api/horario/whitelist"),
  );

export const useQosPlan = () =>
  useQuery<QosPlan>(lectura<QosPlan>("qosPlan", "/api/qos/plan"));

export const useQosDiagnostico = (activo: boolean) =>
  useQuery<QosDiagnostico>({
    ...lectura<QosDiagnostico>("qosDiagnostico", "/api/qos/diagnostico", 15_000),
    enabled: activo,
  });

export const useRespaldos = () =>
  useQuery<RespaldosResp>(lectura<RespaldosResp>("respaldos", "/api/respaldos"));

/** Crear respaldo — no exige confirmar: el snapshot es solo lectura y
 *  el .backup (full) no altera la configuración del router. */
export function useCrearRespaldo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { full: boolean }) =>
      apiPost<RespaldoCreado>("/api/respaldos", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["respaldos"] });
    },
  });
}

/** Mutación de escritura ⚠️: siempre envía confirmar:true e invalida
 *  las lecturas afectadas al terminar. */
function escritura<TBody>(
  ejecutar: (body: TBody) => Promise<{ mensaje: string }>,
  invalidar: string[],
) {
  return () => {
    const qc = useQueryClient();
    return useMutation({
      mutationFn: ejecutar,
      onSuccess: () => {
        for (const key of invalidar) {
          void qc.invalidateQueries({ queryKey: [key] });
        }
      },
    });
  };
}

export const useBloquear = escritura(
  (body: { ip: string }) =>
    apiPost<{ mensaje: string }>("/api/bloqueos", { ...body, confirmar: true }),
  ["bloqueos"],
);

export const useDesbloquear = escritura(
  (body: { ip: string }) =>
    apiDelete<{ mensaje: string }>(`/api/bloqueos/${body.ip}`, {
      confirmar: true,
    }),
  ["bloqueos"],
);

export const useCrearHorario = escritura(
  (body: { inicio: string; fin: string; dias: string[] }) =>
    apiPost<{ mensaje: string }>("/api/horario", { ...body, confirmar: true }),
  ["horario", "whitelist"],
);

export const useEliminarHorario = escritura(
  (_body: Record<string, never>) =>
    apiDelete<{ mensaje: string }>("/api/horario", { confirmar: true }),
  ["horario", "whitelist"],
);

export const useGuardarWhitelist = escritura(
  (body: { macs: string[] }) =>
    apiPut<{ mensaje: string }>("/api/horario/whitelist", {
      ...body,
      confirmar: true,
    }),
  ["horario", "whitelist"],
);

export const useDesplegarQos = escritura(
  (_body: Record<string, never>) =>
    apiPost<{ mensaje: string }>("/api/qos/desplegar", { confirmar: true }),
  ["qosPlan", "qosDiagnostico", "validacion"],
);

export const useResetQos = escritura(
  (_body: Record<string, never>) =>
    apiDelete<{ mensaje: string }>("/api/qos", { confirmar: true }),
  ["qosPlan", "qosDiagnostico", "validacion"],
);

/** ¿El error indica que la sesión expiró? */
export function esSesionExpirada(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
