import { Link } from "react-router-dom";

import {
  useConsumo,
  useHorario,
  useSistema,
  useValidacion,
} from "../api/hooks";
import { Barra, Tarjeta } from "../components/Tarjeta";
import { es } from "../i18n/es";
import { fmtBytes, fmtUptime, fmtVelocidad, porcentaje } from "../lib/formato";

const t = es.dashboard;

function TarjetaRouter() {
  const { data, isLoading, isError } = useSistema();
  return (
    <Tarjeta titulo={t.router} cargando={isLoading} error={isError}>
      {data && (
        <div className="space-y-3">
          <div>
            <div className="text-lg font-semibold text-slate-100">
              {data.name}
            </div>
            <div className="text-xs text-slate-500">
              {data.board} · RouterOS {data.version} · {t.uptime}{" "}
              {fmtUptime(data.uptime)}
            </div>
          </div>
          <div className="space-y-2 text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <span className="w-10">{t.cpu}</span>
              <Barra pct={data.cpu_load} />
              <span className="w-12 text-right">{data.cpu_load}%</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-10">{t.ram}</span>
              <Barra pct={porcentaje(data.used_mem, data.total_mem)} />
              <span className="w-12 text-right">
                {Math.round(porcentaje(data.used_mem, data.total_mem))}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-10">{t.disco}</span>
              <Barra pct={porcentaje(data.used_hdd, data.total_hdd)} />
              <span className="w-12 text-right">
                {Math.round(porcentaje(data.used_hdd, data.total_hdd))}%
              </span>
            </div>
          </div>
          <div className="text-xs text-slate-500">
            {t.interfaces(data.ifaces_up, data.ifaces_total)}
          </div>
        </div>
      )}
    </Tarjeta>
  );
}

function TarjetaCorte() {
  const { data, isLoading, isError } = useHorario();
  return (
    <Tarjeta titulo={t.corte} cargando={isLoading} error={isError}>
      {data &&
        (data.corte ? (
          <div className="space-y-2">
            <div
              className={
                data.en_curso
                  ? "font-medium text-rose-400"
                  : "font-medium text-emerald-400"
              }
            >
              {data.en_curso ? t.corteEnCurso : t.corteFuera}
            </div>
            <div className="text-sm text-slate-300">
              {t.corteHorario}{" "}
              <span className="font-semibold">{data.corte.inicio}</span>{" "}
              {t.corteA} <span className="font-semibold">{data.corte.fin}</span>
            </div>
            <div className="text-xs text-slate-500">
              {data.corte.dias_etiquetas.join(", ")}
            </div>
            <div className="text-xs text-slate-500">
              🛡️ {t.whitelistCount(data.whitelist.length)}
            </div>
          </div>
        ) : (
          <div className="text-emerald-400">{t.sinCorte}</div>
        ))}
    </Tarjeta>
  );
}

function TarjetaQos() {
  const { data, isLoading, isError } = useValidacion();
  return (
    <Tarjeta titulo={t.qos} cargando={isLoading} error={isError}>
      {data && (
        <div className="space-y-1">
          <div
            className={
              data.qos.activo
                ? "font-medium text-emerald-400"
                : "font-medium text-slate-400"
            }
          >
            {data.qos.activo ? t.qosActivo : t.qosInactivo}
          </div>
          <div className="text-xs text-slate-500">
            {t.qosDetalle(data.qos.mangle, data.qos.queue_tree)}
          </div>
        </div>
      )}
    </Tarjeta>
  );
}

function TarjetaConsumo() {
  const { data, isLoading, isError } = useConsumo(5);
  return (
    <Tarjeta titulo={t.topConsumo} cargando={isLoading} error={isError}>
      {data &&
        (data.dispositivos.length === 0 ? (
          <div className="text-sm text-slate-500">{t.sinConsumo}</div>
        ) : (
          <ul className="space-y-2">
            {data.dispositivos.map((d, i) => (
              <li key={d.ip} className="flex items-center gap-2 text-sm">
                <span className="w-5 text-slate-600">{i + 1}</span>
                <span className="flex-1 truncate text-slate-200">
                  {d.nombre}
                </span>
                <span className="text-xs text-sky-300">
                  ↓ {fmtVelocidad(d.dl_rate)}
                </span>
                <span className="hidden text-xs text-slate-500 sm:inline">
                  {fmtBytes(d.dl_total)}
                </span>
              </li>
            ))}
          </ul>
        ))}
    </Tarjeta>
  );
}

function TarjetaDispositivos() {
  const { data, isLoading, isError } = useSistema();
  return (
    <Tarjeta titulo={t.dispositivos} cargando={isLoading} error={isError}>
      {data && (
        <div className="flex items-end justify-between">
          <div>
            <div className="text-3xl font-semibold text-slate-100">
              {data.devices_conn}
            </div>
            <div className="text-xs text-slate-500">
              {t.conectados(data.devices_conn)}
            </div>
          </div>
          <Link to="/dispositivos" className="text-sm text-sky-400">
            {t.verTodos}
          </Link>
        </div>
      )}
    </Tarjeta>
  );
}

export function Dashboard() {
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-slate-100">{t.titulo}</h1>
      <div className="grid gap-4 sm:grid-cols-2">
        <TarjetaRouter />
        <TarjetaCorte />
        <TarjetaConsumo />
        <div className="grid gap-4">
          <TarjetaQos />
          <TarjetaDispositivos />
        </div>
      </div>
    </div>
  );
}
