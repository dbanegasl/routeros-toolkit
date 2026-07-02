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

import { apiGet, apiPost, ApiError } from "./client";
import type {
  Consumo,
  DispositivosResp,
  Horario,
  Sesion,
  Sistema,
  Validacion,
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

export const useConsumo = (top = 5) =>
  useQuery<Consumo>(
    lectura<Consumo>("consumo", `/api/consumo?top=${top}`, 15_000),
  );

/** ¿El error indica que la sesión expiró? */
export function esSesionExpirada(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
