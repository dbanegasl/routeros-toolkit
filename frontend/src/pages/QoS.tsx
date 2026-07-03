/**
 * QoS — estado, visor del plan (dry-run), desplegar ⚠️, diagnóstico
 * con contadores reales, monitor en vivo (/ws/qos) y reset ⚠️.
 *
 * El plan que se muestra es EXACTAMENTE el que aplica el despliegue
 * (mismos builders de core/qos.py que el CLI).
 */
import { useState } from "react";

import {
  useDesplegarQos,
  useQosDiagnostico,
  useQosPlan,
  useResetQos,
} from "../api/hooks";
import type { QosMsg, ReglaRouterOS } from "../api/types";
import { useWs } from "../api/ws";
import { Confirmar } from "../components/Confirmar";
import { es } from "../i18n/es";
import { fmtBytes, fmtVelocidad } from "../lib/formato";

const t = es.qos;

type Accion = "desplegar" | "reset";

function Badge({ ok, texto }: { ok: boolean; texto: string }) {
  return (
    <span
      className={[
        "rounded-full px-2.5 py-1 text-xs",
        ok ? "bg-emerald-500/10 text-emerald-400" : "bg-slate-800 text-slate-400",
      ].join(" ")}
    >
      {texto}
    </span>
  );
}

function Seccion({
  titulo,
  children,
}: {
  titulo: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-4 rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-sm font-medium text-slate-400">{titulo}</h2>
      {children}
    </section>
  );
}

/** Detalle de una regla Mangle sin las claves ya visibles. */
function detalleRegla(r: ReglaRouterOS): string {
  return Object.entries(r)
    .filter(([k]) => k !== "comment")
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
}

function PlanMangle({ reglas }: { reglas: ReglaRouterOS[] }) {
  return (
    <details>
      <summary className="cursor-pointer select-none text-sm text-sky-300">
        {t.reglasMangle(reglas.length)}
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="pb-2 pr-3">#</th>
              <th className="pb-2 pr-3">{t.colRegla}</th>
              <th className="pb-2">{t.colDetalle}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {reglas.map((r, i) => (
              <tr key={r.comment}>
                <td className="py-2 pr-3 text-slate-600">{i + 1}</td>
                <td className="py-2 pr-3 text-slate-200">{r.comment}</td>
                <td className="py-2 font-mono text-xs text-slate-500">
                  {detalleRegla(r)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function PlanColas({ colas }: { colas: ReglaRouterOS[] }) {
  return (
    <details>
      <summary className="cursor-pointer select-none text-sm text-sky-300">
        {t.colas(colas.length)}
      </summary>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="pb-2 pr-3">{t.colCola}</th>
              <th className="pb-2 pr-3">{t.colPadre}</th>
              <th className="pb-2 pr-3 text-right">{t.colPrioridad}</th>
              <th className="pb-2 pr-3 text-right">{t.colGarantizado}</th>
              <th className="pb-2 text-right">{t.colMaximo}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {colas.map((q) => (
              <tr key={q.name}>
                <td className="py-2 pr-3 font-mono text-xs text-slate-200">
                  {q.name}
                </td>
                <td className="py-2 pr-3 font-mono text-xs text-slate-500">
                  {q.parent}
                </td>
                <td className="py-2 pr-3 text-right text-slate-400">
                  {q.priority ?? "—"}
                </td>
                <td className="py-2 pr-3 text-right text-slate-300">
                  {q["limit-at"] ?? "—"}
                </td>
                <td className="py-2 text-right text-slate-300">
                  {q["max-limit"] ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function MonitorVivo() {
  const { datos, conectado } = useWs<QosMsg>("/ws/qos");
  const dl = (datos?.colas ?? []).filter((c) => c.nombre.startsWith("DL-"));
  const ul = (datos?.colas ?? []).filter((c) => c.nombre.startsWith("UL-"));

  if (!datos) {
    return <div className="text-sm text-slate-600">{t.sinDatos}</div>;
  }
  return (
    <div>
      <div className="mb-2 text-right text-xs text-slate-500">
        {conectado ? es.monitoreo.conectado : es.monitoreo.conectando}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {[
          { titulo: t.descarga, colas: dl },
          { titulo: t.subida, colas: ul },
        ].map((grupo) => (
          <div key={grupo.titulo} className="overflow-x-auto">
            <h3 className="mb-2 text-xs uppercase text-slate-500">
              {grupo.titulo}
            </h3>
            <table className="w-full min-w-[380px] text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="pb-2 pr-2">{t.colCola}</th>
                  <th className="pb-2 pr-2 text-right">{t.colVelocidad}</th>
                  <th className="pb-2 pr-2 text-right">{t.colTotal}</th>
                  <th className="pb-2 text-right">{t.colDescartados}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {grupo.colas.map((c) => (
                  <tr key={c.nombre}>
                    <td className="py-2 pr-2 font-mono text-xs text-slate-200">
                      {c.nombre}
                    </td>
                    <td className="py-2 pr-2 text-right text-sky-300">
                      {fmtVelocidad(c.rate)}
                    </td>
                    <td className="py-2 pr-2 text-right text-slate-400">
                      {fmtBytes(c.bytes)}
                    </td>
                    <td
                      className={[
                        "py-2 text-right",
                        c.descartados > 0 ? "text-amber-400" : "text-slate-600",
                      ].join(" ")}
                    >
                      {c.descartados}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}

export function QoS() {
  const plan = useQosPlan();
  const activo = plan.data?.estado.activo ?? false;
  const diagnostico = useQosDiagnostico(activo);
  const desplegar = useDesplegarQos();
  const reset = useResetQos();
  const [accion, setAccion] = useState<Accion | null>(null);

  const mutando = desplegar.isPending || reset.isPending;

  function ejecutar() {
    const mutacion = accion === "desplegar" ? desplegar : reset;
    mutacion.mutate({}, { onSettled: () => setAccion(null) });
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-100">{t.titulo}</h1>
        {plan.data && (
          <div className="flex items-center gap-2">
            <Badge ok={activo} texto={activo ? t.activo : t.inactivo} />
            <Badge
              ok={!plan.data.estado.fasttrack_activo}
              texto={
                plan.data.estado.fasttrack_activo
                  ? t.fasttrackOn
                  : t.fasttrackOff
              }
            />
          </div>
        )}
      </div>

      {plan.isLoading && (
        <div className="animate-pulse text-sm text-slate-600">
          {es.errores.cargando}
        </div>
      )}
      {plan.isError && (
        <div className="text-sm text-rose-400">{es.errores.generico}</div>
      )}

      {plan.data && (
        <>
          {/* Acciones ⚠️ */}
          <div className="mb-4 flex flex-wrap gap-2">
            <button
              onClick={() => setAccion("desplegar")}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
            >
              ⚠️ {t.desplegar}
            </button>
            {activo && (
              <button
                onClick={() => setAccion("reset")}
                className="rounded-lg bg-rose-600/20 px-4 py-2 text-sm font-medium text-rose-300 hover:bg-rose-600/30"
              >
                ⚠️ {t.reset}
              </button>
            )}
          </div>

          {activo && (
            <div className="mb-4 text-xs text-slate-500">
              {t.resumenEstado(
                plan.data.estado.mangle_qos,
                plan.data.estado.colas_qos,
              )}
              {(plan.data.estado.mangle_ajenas > 0 ||
                plan.data.estado.colas_ajenas > 0) && (
                <>
                  {" · "}
                  {t.ajenas(
                    plan.data.estado.mangle_ajenas,
                    plan.data.estado.colas_ajenas,
                  )}
                </>
              )}
            </div>
          )}

          {/* Plan dry-run */}
          <Seccion titulo={t.plan}>
            <p className="mb-3 text-xs text-slate-500">{t.planAyuda}</p>
            <div className="mb-4 grid gap-3 text-sm sm:grid-cols-3">
              <div>
                <div className="text-xs uppercase text-slate-500">
                  {t.dispositivo}
                </div>
                <div className="text-slate-200">
                  {plan.data.config.dispositivo.nombre}
                </div>
                <div className="font-mono text-xs text-slate-500">
                  {plan.data.config.dispositivo.ip} ·{" "}
                  {plan.data.config.dispositivo.mac}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {plan.data.lease.existe
                    ? t.leaseOk(plan.data.lease.ip_actual ?? "")
                    : t.leaseFalta}
                </div>
              </div>
              <div>
                <div className="text-xs uppercase text-slate-500">
                  {plan.data.config.interfaz_wan} · {plan.data.config.bridge_lan}
                </div>
                <div className="text-slate-200">
                  {t.anchoBanda(
                    plan.data.config.descarga_total_mbps,
                    plan.data.config.subida_total_mbps,
                  )}
                </div>
              </div>
              <div className="text-xs text-slate-500 sm:self-end">
                {t.umbral(plan.data.config.umbral_bulk_mb)}
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <PlanMangle reglas={plan.data.mangle} />
              <PlanColas colas={plan.data.colas} />
            </div>
          </Seccion>

          {/* Diagnóstico + monitor (solo con QoS desplegado) */}
          {!activo && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-6 text-center text-sm text-slate-500">
              {t.sinDesplegar}
            </div>
          )}

          {activo && diagnostico.data && (
            <Seccion titulo={t.diagnostico}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-left text-sm">
                  <thead className="text-xs uppercase text-slate-500">
                    <tr>
                      <th className="pb-2 pr-3">{t.colMarca}</th>
                      <th className="pb-2 pr-3 text-right">{t.colBytes}</th>
                      <th className="pb-2 text-right">{t.colPaquetes}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {diagnostico.data.marcas.map((m) => (
                      <tr key={m.prioridad}>
                        <td className="py-2 pr-3 text-slate-200">
                          {m.prioridad}
                        </td>
                        <td className="py-2 pr-3 text-right text-slate-300">
                          {fmtBytes(m.bytes)}
                        </td>
                        <td className="py-2 text-right text-slate-500">
                          {m.paquetes.toLocaleString("es")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Seccion>
          )}

          {activo && (
            <Seccion titulo={t.monitor}>
              <MonitorVivo />
            </Seccion>
          )}
        </>
      )}

      <Confirmar
        abierto={accion !== null}
        titulo={accion === "desplegar" ? t.tituloDesplegar : t.tituloReset}
        ocupado={mutando}
        onCancelar={() => setAccion(null)}
        onConfirmar={ejecutar}
      >
        {accion === "desplegar" && plan.data
          ? t.msjDesplegar(
              plan.data.config.dispositivo.nombre,
              plan.data.mangle.length,
              plan.data.colas.length,
            )
          : t.msjReset}
      </Confirmar>
    </div>
  );
}
