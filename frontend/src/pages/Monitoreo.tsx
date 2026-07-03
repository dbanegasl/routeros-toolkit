/**
 * Monitoreo — datos en vivo por /ws/monitor (un muestreo compartido en
 * el backend). Una gráfica (tráfico total ↓/↑, mismo eje bps) y tablas
 * para dispositivos e interfaces.
 */
import { useEffect, useRef, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MonitorMsg } from "../api/types";
import { useWs } from "../api/ws";
import { es } from "../i18n/es";
import { fmtBytes, fmtVelocidad } from "../lib/formato";

const t = es.monitoreo;

// Paleta validada para superficie oscura (dataviz: slots 1 y 2, dark)
const COLOR_DESCARGA = "#3987e5";
const COLOR_SUBIDA = "#199e70";
const VENTANA = 60; // muestras retenidas (~3 min a 3 s)

interface Punto {
  hora: string;
  descarga: number;
  subida: number;
}

function EstadoConexion({ conectado }: { conectado: boolean }) {
  return (
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
      {conectado ? t.conectado : t.conectando}
    </span>
  );
}

function GraficaTrafico({ puntos }: { puntos: Punto[] }) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={puntos} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="#1e293b" vertical={false} />
          <XAxis
            dataKey="hora"
            tick={{ fill: "#64748b", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#1e293b" }}
            minTickGap={48}
          />
          <YAxis
            tickFormatter={(v: number) => fmtVelocidad(v)}
            tick={{ fill: "#64748b", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={78}
          />
          <Tooltip
            formatter={(valor, nombre) => [fmtVelocidad(Number(valor)), nombre]}
            contentStyle={{
              backgroundColor: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#94a3b8" }}
          />
          <Legend
            formatter={(valor: string) => (
              <span style={{ color: "#94a3b8", fontSize: 12 }}>{valor}</span>
            )}
          />
          <Line
            type="monotone"
            dataKey="descarga"
            name={`↓ ${t.descarga}`}
            stroke={COLOR_DESCARGA}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="subida"
            name={`↑ ${t.subida}`}
            stroke={COLOR_SUBIDA}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Monitoreo() {
  const { datos, conectado } = useWs<MonitorMsg>("/ws/monitor");
  const [puntos, setPuntos] = useState<Punto[]>([]);
  const ultimoTs = useRef(0);

  useEffect(() => {
    if (!datos || datos.error || datos.ts === ultimoTs.current) return;
    ultimoTs.current = datos.ts;
    const hora = new Date(datos.ts * 1000).toLocaleTimeString("es", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    const descarga = datos.dispositivos.reduce((s, d) => s + d.dl_rate, 0);
    const subida = datos.dispositivos.reduce((s, d) => s + d.ul_rate, 0);
    setPuntos((prev) => [...prev, { hora, descarga, subida }].slice(-VENTANA));
  }, [datos]);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-100">{t.titulo}</h1>
        <EstadoConexion conectado={conectado} />
      </div>

      {datos?.error && (
        <div className="mb-4 rounded-lg border border-rose-900 bg-rose-950/40 px-4 py-2 text-sm text-rose-300">
          {datos.error}
        </div>
      )}

      <section className="mb-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
        <h2 className="mb-2 text-sm font-medium text-slate-400">{t.trafico}</h2>
        {puntos.length === 0 ? (
          <div className="grid h-64 place-items-center text-sm text-slate-600">
            {t.sinDatos}
          </div>
        ) : (
          <GraficaTrafico puntos={puntos} />
        )}
        {datos && (
          <div className="mt-2 text-xs text-slate-500">
            {t.conexiones(datos.conexiones_totales)}
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-400">
            {t.dispositivos}
          </h2>
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="pb-2 pr-2">{t.colDispositivo}</th>
                <th className="pb-2 pr-2 text-right">{t.colDescarga}</th>
                <th className="pb-2 pr-2 text-right">{t.colSubida}</th>
                <th className="pb-2 pr-2 text-right">{t.colSesion}</th>
                <th className="pb-2 text-right">{t.colConn}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {(datos?.dispositivos ?? []).slice(0, 12).map((d) => (
                <tr key={d.ip}>
                  <td className="max-w-[180px] truncate py-2 pr-2 text-slate-200">
                    {d.nombre}
                  </td>
                  <td className="py-2 pr-2 text-right"
                    style={{ color: COLOR_DESCARGA }}>
                    {fmtVelocidad(d.dl_rate)}
                  </td>
                  <td className="py-2 pr-2 text-right"
                    style={{ color: COLOR_SUBIDA }}>
                    {fmtVelocidad(d.ul_rate)}
                  </td>
                  <td className="py-2 pr-2 text-right text-slate-400">
                    {fmtBytes(d.dl_total)}
                  </td>
                  <td className="py-2 text-right text-slate-500">
                    {d.conexiones}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <h2 className="mb-3 text-sm font-medium text-slate-400">
            {t.interfaces}
          </h2>
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="pb-2 pr-2">{t.colInterfaz}</th>
                <th className="pb-2 pr-2 text-right">{t.colTx}</th>
                <th className="pb-2 pr-2 text-right">{t.colRx}</th>
                <th className="pb-2 pr-2 text-right">{t.colTxTotal}</th>
                <th className="pb-2 text-right">{t.colRxTotal}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {(datos?.interfaces ?? []).map((i) => (
                <tr key={i.nombre}
                  className={i.activa ? "" : "opacity-40"}>
                  <td className="py-2 pr-2 font-mono text-xs text-slate-200">
                    {i.nombre}
                  </td>
                  <td className="py-2 pr-2 text-right text-slate-300">
                    {fmtVelocidad(i.tx_rate)}
                  </td>
                  <td className="py-2 pr-2 text-right text-slate-300">
                    {fmtVelocidad(i.rx_rate)}
                  </td>
                  <td className="py-2 pr-2 text-right text-slate-500">
                    {fmtBytes(i.tx_total)}
                  </td>
                  <td className="py-2 text-right text-slate-500">
                    {fmtBytes(i.rx_total)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
