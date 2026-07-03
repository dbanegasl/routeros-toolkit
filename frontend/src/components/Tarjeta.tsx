/**
 * Tarjeta — contenedor de las tarjetas del Dashboard, con estados de
 * carga y error uniformes.
 */
import type { ReactNode } from "react";

import { es } from "../i18n/es";

interface Props {
  titulo: string;
  cargando?: boolean;
  error?: boolean;
  children: ReactNode;
}

export function Tarjeta({ titulo, cargando, error, children }: Props) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-sm font-medium text-slate-400">{titulo}</h2>
      {cargando ? (
        <div className="animate-pulse text-sm text-slate-600">
          {es.errores.cargando}
        </div>
      ) : error ? (
        <div className="text-sm text-rose-400">{es.errores.generico}</div>
      ) : (
        children
      )}
    </section>
  );
}

export function Barra({ pct, alerta }: { pct: number; alerta?: boolean }) {
  const color =
    pct > 85 ? "bg-rose-500" : pct > 60 || alerta ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
      <div className={`h-full rounded-full ${color}`}
        style={{ width: `${pct}%` }} />
    </div>
  );
}
