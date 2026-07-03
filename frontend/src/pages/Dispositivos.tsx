import { useMemo, useState } from "react";

import {
  useBloquear,
  useBloqueos,
  useDesbloquear,
  useDispositivos,
} from "../api/hooks";
import { Confirmar } from "../components/Confirmar";
import { es } from "../i18n/es";

const t = es.dispositivos;

interface AccionPendiente {
  tipo: "bloquear" | "desbloquear";
  ip: string;
  nombre: string;
}

type Filtro = "todos" | "DHCP" | "STATIC";

const FILTROS: { valor: Filtro; texto: string }[] = [
  { valor: "todos", texto: t.filtroTodos },
  { valor: "DHCP", texto: t.filtroDhcp },
  { valor: "STATIC", texto: t.filtroEstatica },
];

function colorEstado(estado: string): string {
  if (estado === "bound") return "text-emerald-400";
  if (estado === "estática") return "text-amber-400";
  return "text-slate-400";
}

export function Dispositivos() {
  const { data, isLoading, isError } = useDispositivos();
  const bloqueos = useBloqueos();
  const bloquear = useBloquear();
  const desbloquear = useDesbloquear();
  const [busqueda, setBusqueda] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todos");
  const [accion, setAccion] = useState<AccionPendiente | null>(null);

  const ipsBloqueadas = useMemo(
    () => new Set((bloqueos.data?.bloqueos ?? []).map((b) => b.ip)),
    [bloqueos.data],
  );
  const mutando = bloquear.isPending || desbloquear.isPending;

  function ejecutarAccion() {
    if (!accion) return;
    const mutacion = accion.tipo === "bloquear" ? bloquear : desbloquear;
    mutacion.mutate(
      { ip: accion.ip },
      { onSettled: () => setAccion(null) },
    );
  }

  const filtrados = useMemo(() => {
    const lista = data?.dispositivos ?? [];
    const q = busqueda.trim().toLowerCase();
    return lista.filter((d) => {
      if (filtro !== "todos" && d.tipo !== filtro) return false;
      if (!q) return true;
      return [d.nombre, d.ip, d.mac].some((campo) =>
        campo.toLowerCase().includes(q),
      );
    });
  }, [data, busqueda, filtro]);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-slate-100">{t.titulo}</h1>

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          type="search"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder={t.buscar}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-sky-500"
        />
        <div className="flex gap-2">
          {FILTROS.map((f) => (
            <button
              key={f.valor}
              onClick={() => setFiltro(f.valor)}
              className={[
                "rounded-full px-3 py-1.5 text-xs transition-colors",
                filtro === f.valor
                  ? "bg-sky-500/20 text-sky-300"
                  : "bg-slate-800 text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {f.texto}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="animate-pulse text-sm text-slate-600">
          {es.errores.cargando}
        </div>
      )}
      {isError && (
        <div className="text-sm text-rose-400">{es.errores.generico}</div>
      )}

      {data && (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-slate-900 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">{t.colIp}</th>
                  <th className="px-4 py-3">{t.colNombre}</th>
                  <th className="px-4 py-3">{t.colMac}</th>
                  <th className="px-4 py-3">{t.colEstado}</th>
                  <th className="px-4 py-3">{t.colPuerto}</th>
                  <th className="px-4 py-3">{t.colTipo}</th>
                  <th className="px-4 py-3">{t.colAcciones}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {filtrados.map((d) => {
                  const bloqueada = ipsBloqueadas.has(d.ip);
                  return (
                    <tr key={`${d.ip}-${d.mac}`}
                      className="hover:bg-slate-900/50">
                      <td className="px-4 py-2.5 font-mono text-cyan-300">
                        {d.ip}
                        {bloqueada && (
                          <span className="ml-2 text-xs text-rose-400">
                            {t.bloqueada}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-slate-200">{d.nombre}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500">
                        {d.mac || "—"}
                      </td>
                      <td className={`px-4 py-2.5 ${colorEstado(d.estado)}`}>
                        {d.estado}
                      </td>
                      <td className="px-4 py-2.5 text-slate-400">{d.puerto}</td>
                      <td className="px-4 py-2.5 text-xs text-slate-500">
                        {d.tipo}
                      </td>
                      <td className="px-4 py-2.5">
                        <button
                          onClick={() =>
                            setAccion({
                              tipo: bloqueada ? "desbloquear" : "bloquear",
                              ip: d.ip,
                              nombre: d.nombre,
                            })
                          }
                          className={[
                            "rounded-lg px-2.5 py-1 text-xs font-medium",
                            bloqueada
                              ? "bg-emerald-600/20 text-emerald-300 hover:bg-emerald-600/30"
                              : "bg-rose-600/20 text-rose-300 hover:bg-rose-600/30",
                          ].join(" ")}
                        >
                          {bloqueada ? t.desbloquear : `⚠️ ${t.bloquear}`}
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {filtrados.length === 0 && (
                  <tr>
                    <td colSpan={7}
                      className="px-4 py-8 text-center text-slate-500">
                      {t.vacio}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="mt-3 text-xs text-slate-500">
            {t.total(filtrados.length)}
          </div>
        </>
      )}

      <Confirmar
        abierto={accion !== null}
        titulo={accion?.tipo === "bloquear"
          ? t.tituloBloquear : t.tituloDesbloquear}
        peligro={accion?.tipo === "bloquear"}
        ocupado={mutando}
        onCancelar={() => setAccion(null)}
        onConfirmar={ejecutarAccion}
      >
        {accion &&
          (accion.tipo === "bloquear"
            ? t.msjBloquear(accion.nombre, accion.ip)
            : t.msjDesbloquear(accion.nombre, accion.ip))}
      </Confirmar>
    </div>
  );
}
