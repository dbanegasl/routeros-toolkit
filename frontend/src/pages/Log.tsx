/**
 * Log — visor del syslog del router por /ws/log (follow en vivo).
 * Colores por nivel como mant_log.py; filtro de texto; auto-scroll.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import type { LogEntrada, LogMsg } from "../api/types";
import { useWs } from "../api/ws";
import { es } from "../i18n/es";

const t = es.log;

const COLOR_NIVEL: Record<LogEntrada["nivel"], string> = {
  critical: "text-rose-400",
  error: "text-rose-400",
  warning: "text-amber-400",
  info: "text-slate-300",
  debug: "text-slate-600",
};

const ICONO_NIVEL: Record<LogEntrada["nivel"], string> = {
  critical: "💀",
  error: "🔴",
  warning: "🟡",
  info: "",
  debug: "",
};

export function Log() {
  const { datos, conectado } = useWs<LogMsg>("/ws/log");
  const [filtro, setFiltro] = useState("");
  const [seguir, setSeguir] = useState(true);
  const finRef = useRef<HTMLDivElement>(null);

  const entradas = useMemo(() => {
    const lista = datos?.entradas ?? [];
    const q = filtro.trim().toLowerCase();
    if (!q) return lista;
    return lista.filter((e) =>
      `${e.hora} ${e.topics} ${e.mensaje}`.toLowerCase().includes(q),
    );
  }, [datos, filtro]);

  useEffect(() => {
    if (seguir) finRef.current?.scrollIntoView({ behavior: "instant" });
  }, [entradas, seguir]);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-100">{t.titulo}</h1>
        <span
          className={[
            "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs",
            conectado
              ? "bg-emerald-500/10 text-emerald-400"
              : "bg-slate-800 text-slate-500",
          ].join(" ")}
        >
          <span
            className={[
              "h-1.5 w-1.5 rounded-full",
              conectado ? "animate-pulse bg-emerald-400" : "bg-slate-600",
            ].join(" ")}
          />
          {conectado ? es.monitoreo.conectado : es.monitoreo.conectando}
        </span>
      </div>

      <div className="mb-3 flex items-center gap-3">
        <input
          type="search"
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          placeholder={t.filtrar}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-sky-500"
        />
        <label className="flex items-center gap-2 text-sm text-slate-400">
          <input
            type="checkbox"
            checked={seguir}
            onChange={(e) => setSeguir(e.target.checked)}
            className="accent-sky-500"
          />
          {t.seguir}
        </label>
      </div>

      {datos?.error && (
        <div className="mb-3 rounded-lg border border-rose-900 bg-rose-950/40 px-4 py-2 text-sm text-rose-300">
          {datos.error}
        </div>
      )}

      <div className="max-h-[70vh] overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs leading-relaxed">
        {entradas.length === 0 ? (
          <div className="py-8 text-center text-slate-600">
            {datos ? t.vacio : es.monitoreo.sinDatos}
          </div>
        ) : (
          entradas.map((e, i) => (
            <div key={`${e.hora}-${i}`} className={COLOR_NIVEL[e.nivel]}>
              <span className="text-slate-600">{e.hora}</span>{" "}
              <span className="text-slate-500">[{e.topics}]</span>{" "}
              {ICONO_NIVEL[e.nivel] && `${ICONO_NIVEL[e.nivel]} `}
              {e.mensaje}
            </div>
          ))
        )}
        <div ref={finRef} />
      </div>

      <div className="mt-2 text-xs text-slate-500">
        {t.entradas(entradas.length)}
      </div>
    </div>
  );
}
