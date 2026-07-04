/**
 * Sistema — sys_validar como página: checks con ✓/⚠️/❌ (reloj, NTP,
 * QoS, FastTrack, dispositivo prioritario, interfaces), identidad del
 * router y configuración visible del panel (sin secretos).
 */
import { useConfig, useValidacion } from "../api/hooks";
import type { Validacion } from "../api/types";
import { es } from "../i18n/es";
import { fmtBytes } from "../lib/formato";

const t = es.sistema;

type Nivel = "ok" | "aviso" | "error";

interface Check {
  nombre: string;
  nivel: Nivel;
  detalle: string;
}

const ICONO: Record<Nivel, string> = { ok: "✅", aviso: "⚠️", error: "❌" };
const COLOR: Record<Nivel, string> = {
  ok: "text-emerald-400",
  aviso: "text-amber-400",
  error: "text-rose-400",
};

/** Traduce la validación del backend a la lista de checks del CLI. */
function construirChecks(v: Validacion): Check[] {
  const checks: Check[] = [];

  // Reloj: los cortes por horario dependen de la hora del router
  if (v.reloj.deriva_segundos === null) {
    checks.push({ nombre: t.checkReloj, nivel: "aviso",
                  detalle: t.relojDesconocido });
  } else {
    checks.push({
      nombre: t.checkReloj,
      nivel: v.reloj.sincronizado ? "ok" : "error",
      detalle: v.reloj.sincronizado
        ? t.relojOk(v.reloj.deriva_segundos)
        : t.relojMal(v.reloj.deriva_segundos),
    });
  }

  checks.push({
    nombre: t.checkNtp,
    nivel: v.reloj.ntp_habilitado ? "ok" : "aviso",
    detalle:
      v.reloj.ntp_habilitado === null
        ? t.ntpNa
        : v.reloj.ntp_habilitado
          ? t.ntpOk
          : t.ntpMal,
  });

  checks.push({
    nombre: t.checkQos,
    nivel: "ok",
    detalle: v.qos.activo
      ? t.qosActivo(v.qos.mangle, v.qos.queue_tree)
      : t.qosInactivo,
  });

  // FastTrack: solo es problema si esquiva un QoS desplegado
  const ftActivo = v.fasttrack.some((r) => !r.deshabilitado);
  if (v.fasttrack.length === 0) {
    checks.push({ nombre: t.checkFasttrack, nivel: "ok",
                  detalle: t.fasttrackSinReglas });
  } else if (ftActivo && v.qos.activo) {
    checks.push({ nombre: t.checkFasttrack, nivel: "error",
                  detalle: t.fasttrackConflicto });
  } else {
    checks.push({
      nombre: t.checkFasttrack,
      nivel: "ok",
      detalle: ftActivo ? t.fasttrackActivo : t.fasttrackApagado,
    });
  }

  const prio = v.dispositivo_prioritario;
  checks.push({
    nombre: t.checkPrioritario,
    nivel: prio.lease ? "ok" : "aviso",
    detalle: prio.lease
      ? t.prioritarioOk(prio.nombre, prio.lease.ip)
      : t.prioritarioSinLease(prio.nombre),
  });

  const activas = v.interfaces.filter((i) => i.activa).length;
  checks.push({
    nombre: t.checkInterfaces,
    nivel: activas > 0 ? "ok" : "error",
    detalle: t.interfacesResumen(activas, v.interfaces.length),
  });

  return checks;
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

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-slate-500">{etiqueta}</div>
      <div className="text-sm text-slate-200">{valor}</div>
    </div>
  );
}

export function Sistema() {
  const validacion = useValidacion();
  const config = useConfig();

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-slate-100">{t.titulo}</h1>

      {validacion.isLoading && (
        <div className="animate-pulse text-sm text-slate-600">
          {es.errores.cargando}
        </div>
      )}
      {validacion.isError && (
        <div className="text-sm text-rose-400">{es.errores.generico}</div>
      )}

      {validacion.data && (
        <>
          <Seccion titulo={t.checks}>
            <ul className="divide-y divide-slate-800/70">
              {construirChecks(validacion.data).map((c) => (
                <li key={c.nombre} className="flex items-start gap-3 py-2.5">
                  <span>{ICONO[c.nivel]}</span>
                  <div>
                    <div className="text-sm text-slate-200">{c.nombre}</div>
                    <div className={`text-xs ${COLOR[c.nivel]}`}>
                      {c.detalle}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </Seccion>

          <Seccion titulo={t.identidad}>
            <div className="grid gap-3 sm:grid-cols-3">
              <Dato etiqueta={t.nombre}
                valor={validacion.data.identidad.nombre} />
              <Dato etiqueta={t.version}
                valor={validacion.data.identidad.version} />
              <Dato etiqueta={t.equipo}
                valor={validacion.data.identidad.equipo} />
              <Dato etiqueta={t.cpu}
                valor={`${validacion.data.identidad.cpu} núcleo(s)`} />
              <Dato etiqueta={t.ram}
                valor={fmtBytes(validacion.data.identidad.ram_total)} />
              <Dato etiqueta={t.horaRouter}
                valor={validacion.data.reloj.hora_router ?? "—"} />
            </div>
          </Seccion>

          <div className="grid gap-4 lg:grid-cols-2">
            <Seccion titulo={t.interfaces}>
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="pb-2 pr-2">{t.colInterfaz}</th>
                    <th className="pb-2 pr-2">{t.colActiva}</th>
                    <th className="pb-2 text-right">{t.colMtu}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {validacion.data.interfaces.map((i) => (
                    <tr key={i.nombre} className={i.activa ? "" : "opacity-40"}>
                      <td className="py-2 pr-2 font-mono text-xs text-slate-200">
                        {i.nombre}
                      </td>
                      <td
                        className={[
                          "py-2 pr-2 text-xs",
                          i.activa ? "text-emerald-400" : "text-slate-500",
                        ].join(" ")}
                      >
                        {i.activa ? t.activa : t.inactiva}
                      </td>
                      <td className="py-2 text-right text-slate-500">
                        {i.mtu}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Seccion>

            <Seccion titulo={t.direcciones}>
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="pb-2 pr-2">{t.colDireccion}</th>
                    <th className="pb-2">{t.colInterfaz}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/70">
                  {validacion.data.direcciones.map((d) => (
                    <tr key={`${d.direccion}-${d.interfaz}`}>
                      <td className="py-2 pr-2 font-mono text-xs text-cyan-300">
                        {d.direccion}
                      </td>
                      <td className="py-2 font-mono text-xs text-slate-500">
                        {d.interfaz}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Seccion>
          </div>
        </>
      )}

      {config.data && (
        <Seccion titulo={t.configuracion}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Dato
              etiqueta={t.confRouter}
              valor={`${config.data.router.host}:${config.data.router.port}`}
            />
            <Dato etiqueta={t.confUsuario} valor={config.data.router.usuario} />
            <Dato etiqueta={t.confLan} valor={config.data.lan_prefix} />
            <Dato
              etiqueta={t.confQos}
              valor={t.confQosDetalle(
                config.data.qos.dispositivo_prioritario.nombre,
                config.data.qos.dispositivo_prioritario.ip,
                config.data.qos.descarga_total_mbps,
                config.data.qos.subida_total_mbps,
              )}
            />
          </div>
        </Seccion>
      )}
    </div>
  );
}
