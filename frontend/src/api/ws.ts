/**
 * ws.ts — Hook de WebSocket con reconexión.
 *
 * El backend difunde snapshots (servidor → cliente); el hook entrega el
 * último mensaje parseado y el estado de conexión. Si el servidor cierra
 * con 4401 (sesión inválida) se marca la sesión como cerrada y NO se
 * reintenta: la app vuelve al login.
 */

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { Sesion } from "./types";

const CIERRE_SIN_SESION = 4401;
const REINTENTO_MS = 2500;

export function useWs<T>(path: string): { datos: T | null; conectado: boolean } {
  const [datos, setDatos] = useState<T | null>(null);
  const [conectado, setConectado] = useState(false);
  const qc = useQueryClient();

  useEffect(() => {
    let ws: WebSocket | null = null;
    let timer: number | undefined;
    let desmontado = false;

    function conectar() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}${path}`);
      ws.onopen = () => setConectado(true);
      ws.onmessage = (ev) => setDatos(JSON.parse(ev.data as string) as T);
      ws.onclose = (ev) => {
        setConectado(false);
        if (desmontado) return;
        if (ev.code === CIERRE_SIN_SESION) {
          qc.setQueryData<Sesion>(["sesion"], { autenticada: false });
          return;
        }
        timer = window.setTimeout(conectar, REINTENTO_MS);
      };
    }

    conectar();
    return () => {
      desmontado = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, [path, qc]);

  return { datos, conectado };
}
