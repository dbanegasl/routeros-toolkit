/**
 * Respaldos — snapshots locales (JSON en el servidor) y .backup
 * completos en el router. Espeja mant_respaldo.py.
 */
import { useState } from "react";

import { useCrearRespaldo, useRespaldos } from "../api/hooks";
import { es } from "../i18n/es";
import { fmtBytes } from "../lib/formato";

const t = es.respaldos;

/** Días transcurridos desde el snapshot más reciente (locales[0]). */
function diasDesdeUltimo(creado?: string): number | null {
  if (!creado) return null;
  const ms = Date.now() - new Date(creado).getTime();
  if (Number.isNaN(ms)) return null;
  return Math.max(0, Math.floor(ms / 86_400_000));
}

export function Respaldos() {
  const { data, isLoading, isError } = useRespaldos();
  const crear = useCrearRespaldo();
  const [mensaje, setMensaje] = useState<string | null>(null);

  const dias = diasDesdeUltimo(data?.locales[0]?.meta?.creado);

  function crearRespaldo(full: boolean) {
    setMensaje(null);
    crear.mutate(
      { full },
      { onSuccess: (r) => setMensaje(r.mensaje) },
    );
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-100">{t.titulo}</h1>
        {data && (
          <span
            className={[
              "rounded-full px-2.5 py-1 text-xs",
              dias === null
                ? "bg-amber-500/10 text-amber-400"
                : "bg-emerald-500/10 text-emerald-400",
            ].join(" ")}
          >
            {dias === null ? t.nunca : t.ultimo(dias)}
          </span>
        )}
      </div>

      <p className="mb-4 max-w-2xl text-xs text-slate-500">{t.ayuda}</p>

      <div className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => crearRespaldo(false)}
          disabled={crear.isPending}
          className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {crear.isPending ? t.creando : t.crear}
        </button>
        <button
          onClick={() => crearRespaldo(true)}
          disabled={crear.isPending}
          className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          {crear.isPending ? t.creando : t.crearFull}
        </button>
      </div>

      {mensaje && (
        <div className="mb-4 rounded-lg border border-emerald-900 bg-emerald-950/40 px-4 py-2 text-sm text-emerald-300">
          ✅ {mensaje}
        </div>
      )}
      {crear.isError && (
        <div className="mb-4 rounded-lg border border-rose-900 bg-rose-950/40 px-4 py-2 text-sm text-rose-300">
          {es.errores.generico}
        </div>
      )}

      {isLoading && (
        <div className="animate-pulse text-sm text-slate-600">
          {es.errores.cargando}
        </div>
      )}
      {isError && (
        <div className="text-sm text-rose-400">{es.errores.generico}</div>
      )}

      {data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <section className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-400">
              {t.locales}
            </h2>
            {data.locales.length === 0 ? (
              <div className="text-sm text-slate-600">{t.vacioLocales}</div>
            ) : (
              <table className="w-full min-w-[420px] text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="pb-2 pr-2">{t.colNombre}</th>
                    <th className="pb-2 pr-2 text-right">{t.colTamano}</th>
                    <th className="pb-2 text-right">{t.colRouterOS}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {data.locales.map((s) => (
                    <tr key={s.nombre}>
                      <td className="py-2 pr-2 font-mono text-xs text-slate-200">
                        {s.nombre}
                      </td>
                      <td className="py-2 pr-2 text-right text-slate-400">
                        {fmtBytes(s.bytes)}
                      </td>
                      <td className="py-2 text-right text-slate-500">
                        {s.meta ? (s.meta.routeros ?? "?") : t.ilegible}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-400">
              {t.enRouter}
            </h2>
            {data.router.length === 0 ? (
              <div className="text-sm text-slate-600">{t.vacioRouter}</div>
            ) : (
              <>
                <table className="w-full min-w-[420px] text-left text-sm">
                  <thead className="text-xs uppercase text-slate-500">
                    <tr>
                      <th className="pb-2 pr-2">{t.colNombre}</th>
                      <th className="pb-2 pr-2 text-right">{t.colTamano}</th>
                      <th className="pb-2 text-right">{t.colCreado}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {data.router.map((f) => (
                      <tr key={f.nombre}>
                        <td className="py-2 pr-2 font-mono text-xs text-slate-200">
                          {f.nombre}
                        </td>
                        <td className="py-2 pr-2 text-right text-slate-400">
                          {fmtBytes(f.bytes)}
                        </td>
                        <td className="py-2 text-right text-slate-500">
                          {f.creado}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 text-xs text-slate-600">
                  {t.descargaWinbox}
                </p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
