/**
 * Horario — corte de internet por horario ⚠️
 * Estado del corte, editor (crear/reemplazar), lista blanca con toggles
 * y eliminación. Toda escritura pasa por el diálogo Confirmar.
 */
import { useEffect, useMemo, useState } from "react";

import {
  useAfectados,
  useCrearHorario,
  useDispositivos,
  useEliminarHorario,
  useGuardarWhitelist,
  useHorario,
  useWhitelist,
} from "../api/hooks";
import { Confirmar } from "../components/Confirmar";
import { EditarAlias } from "../components/EditarAlias";
import { es } from "../i18n/es";

const t = es.horario;

const DIAS: { valor: string; texto: string }[] = [
  { valor: "mon", texto: "Lun" },
  { valor: "tue", texto: "Mar" },
  { valor: "wed", texto: "Mié" },
  { valor: "thu", texto: "Jue" },
  { valor: "fri", texto: "Vie" },
  { valor: "sat", texto: "Sáb" },
  { valor: "sun", texto: "Dom" },
];

function EstadoCorte() {
  const { data } = useHorario();
  if (!data) return null;

  if (!data.corte) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-emerald-400">
        {t.sinCorte}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-2 text-sm font-medium text-slate-400">{t.estado}</div>
      <div
        className={
          data.en_curso
            ? "mb-2 font-medium text-rose-400"
            : "mb-2 font-medium text-emerald-400"
        }
      >
        {data.en_curso ? es.dashboard.corteEnCurso : es.dashboard.corteFuera}
      </div>
      <div className="text-2xl font-semibold text-slate-100">
        {data.corte.inicio} → {data.corte.fin}
      </div>
      <div className="mt-1 text-sm text-slate-400">
        {data.corte.dias_etiquetas.join(", ")}
      </div>
      <div className="mt-2 text-xs text-slate-500">
        WAN: {data.corte.interfaz_wan} ·{" "}
        {t.paquetes(data.corte.paquetes_bloqueados)}
      </div>
    </div>
  );
}

function Editor() {
  const { data } = useHorario();
  const crear = useCrearHorario();
  const [inicio, setInicio] = useState("01:00");
  const [fin, setFin] = useState("06:00");
  const [dias, setDias] = useState<string[]>([]);
  const [confirmando, setConfirmando] = useState(false);

  const whitelistN = data?.whitelist.length ?? 0;
  const hayCorte = Boolean(data?.corte);

  // Precargar el horario vigente en el editor
  useEffect(() => {
    if (data?.corte) {
      setInicio(data.corte.inicio);
      setFin(data.corte.fin);
      setDias(data.corte.dias.length === 7 ? [] : data.corte.dias);
    }
  }, [data?.corte]);

  function toggleDia(d: string) {
    setDias((prev) =>
      prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d],
    );
  }

  const etiquetaDias = dias.length === 0
    ? t.todosLosDias
    : DIAS.filter((d) => dias.includes(d.valor)).map((d) => d.texto).join(", ");

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-3 text-sm font-medium text-slate-400">
        {hayCorte ? t.editorReemplazar : t.editor}
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <label className="text-slate-300">{t.inicio}</label>
        <input type="time" value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-slate-100" />
        <label className="text-slate-300">{t.fin}</label>
        <input type="time" value={fin}
          onChange={(e) => setFin(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-slate-100" />
      </div>

      <div className="mb-1 text-sm text-slate-300">{t.dias}</div>
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          onClick={() => setDias([])}
          className={[
            "rounded-full px-3 py-1.5 text-xs",
            dias.length === 0
              ? "bg-sky-500/20 text-sky-300"
              : "bg-slate-800 text-slate-400",
          ].join(" ")}
        >
          {t.todosLosDias}
        </button>
        {DIAS.map((d) => (
          <button key={d.valor} onClick={() => toggleDia(d.valor)}
            className={[
              "rounded-full px-3 py-1.5 text-xs",
              dias.includes(d.valor)
                ? "bg-sky-500/20 text-sky-300"
                : "bg-slate-800 text-slate-400",
            ].join(" ")}
          >
            {d.texto}
          </button>
        ))}
      </div>

      {crear.isError && (
        <p className="mb-3 text-sm text-rose-400">
          {crear.error instanceof Error ? crear.error.message : ""}
        </p>
      )}
      {crear.isSuccess && !confirmando && (
        <p className="mb-3 text-sm text-emerald-400">{t.hecho}</p>
      )}

      <button
        onClick={() => setConfirmando(true)}
        disabled={!inicio || !fin}
        className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-500 disabled:opacity-50"
      >
        ⚠️ {t.aplicar}
      </button>

      <Confirmar
        abierto={confirmando}
        titulo={t.tituloCrear}
        ocupado={crear.isPending}
        onCancelar={() => setConfirmando(false)}
        onConfirmar={() =>
          crear.mutate(
            { inicio, fin, dias },
            { onSettled: () => setConfirmando(false) },
          )
        }
      >
        {t.msjCrear(inicio, fin, etiquetaDias, whitelistN)}
      </Confirmar>
    </div>
  );
}

interface FilaWhitelist {
  mac: string;
  nombre: string;
  nombre_detectado: string;
  alias: string;
  ip: string | null;
  en_red: boolean;
}

function ListaBlanca() {
  const whitelist = useWhitelist();
  const red = useDispositivos();
  const guardar = useGuardarWhitelist();
  const [marcadas, setMarcadas] = useState<Set<string> | null>(null);
  const [confirmando, setConfirmando] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [editando, setEditando] = useState<FilaWhitelist | null>(null);

  // Filas: todos los dispositivos de la red ∪ whitelist (los offline
  // también, para poder quitarlos), como el --allow del CLI.
  const filas = useMemo<FilaWhitelist[]>(() => {
    const porMac = new Map<string, FilaWhitelist>();
    for (const d of red.data?.dispositivos ?? []) {
      if (!d.mac) continue;
      porMac.set(d.mac.toUpperCase(), {
        mac: d.mac.toUpperCase(),
        nombre: d.nombre,
        nombre_detectado: d.nombre_detectado,
        alias: d.alias,
        ip: d.ip,
        en_red: true,
      });
    }
    for (const w of whitelist.data?.dispositivos ?? []) {
      if (!porMac.has(w.mac)) {
        porMac.set(w.mac, {
          mac: w.mac,
          nombre: w.nombre,
          nombre_detectado: w.nombre_detectado,
          alias: w.alias,
          ip: w.ip,
          en_red: w.en_red,
        });
      }
    }
    return [...porMac.values()].sort((a, b) =>
      (a.ip ?? "z").localeCompare(b.ip ?? "z", "es", { numeric: true }),
    );
  }, [red.data, whitelist.data]);

  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return filas;
    return filas.filter((d) =>
      [d.nombre, d.nombre_detectado, d.ip ?? "", d.mac].some((campo) =>
        campo.toLowerCase().includes(q),
      ),
    );
  }, [filas, busqueda]);

  const originales = useMemo(
    () => new Set((whitelist.data?.dispositivos ?? []).map((d) => d.mac)),
    [whitelist.data],
  );
  const seleccion = marcadas ?? originales;
  const hayCambios =
    marcadas !== null &&
    (marcadas.size !== originales.size ||
      [...marcadas].some((m) => !originales.has(m)));

  function toggle(mac: string) {
    const nueva = new Set(seleccion);
    if (nueva.has(mac)) nueva.delete(mac);
    else nueva.add(mac);
    setMarcadas(nueva);
  }

  if (!whitelist.data) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-slate-400">
          🛡️ {t.whitelist}
        </span>
        <span className="text-xs text-slate-500">
          {t.marcados(seleccion.size, filas.length)}
        </span>
      </div>
      <p className="mb-3 text-xs text-slate-500">{t.whitelistAyuda}</p>

      <input
        type="search"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        placeholder={t.buscar}
        className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-sky-500"
      />

      <div className="mb-4 max-h-[32rem] overflow-auto rounded-lg border border-slate-800">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-900 text-xs uppercase text-slate-500">
            <tr>
              <th className="w-8 px-2 py-2" />
              <th className="px-2 py-2">{t.colNombre}</th>
              <th className="px-2 py-2">{t.colIp}</th>
              <th className="px-2 py-2">{t.colMac}</th>
              <th className="px-2 py-2">{t.colEstado}</th>
              <th className="w-8 px-2 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {visibles.map((d) => (
              <tr
                key={d.mac}
                onClick={() => toggle(d.mac)}
                className="cursor-pointer hover:bg-slate-800/60"
              >
                <td className="px-2 py-1.5">
                  <input
                    type="checkbox"
                    checked={seleccion.has(d.mac)}
                    onChange={() => toggle(d.mac)}
                    onClick={(e) => e.stopPropagation()}
                    aria-label={d.nombre || d.mac}
                    className="accent-emerald-500"
                  />
                </td>
                <td className="max-w-[16rem] px-2 py-1.5">
                  <div className="truncate text-slate-200" title={d.nombre}>
                    {d.nombre || d.mac}
                  </div>
                  {d.alias && d.nombre_detectado && (
                    <div className="truncate text-xs text-slate-500"
                      title={d.nombre_detectado}>
                      {d.nombre_detectado}
                    </div>
                  )}
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 font-mono text-xs text-cyan-300">
                  {d.ip ?? <span className="text-slate-600">—</span>}
                </td>
                <td className="whitespace-nowrap px-2 py-1.5 font-mono text-xs text-slate-500">
                  {d.mac}
                </td>
                <td className="whitespace-nowrap px-2 py-1.5">
                  <span
                    title={d.en_red && d.ip
                      ? t.enRedTooltip(d.ip) : t.offlineTooltip}
                    className={
                      d.en_red
                        ? "text-xs text-emerald-400"
                        : "text-xs text-slate-600"
                    }
                  >
                    {d.en_red ? `● ${t.enRed}` : t.offline}
                  </span>
                </td>
                <td className="px-2 py-1.5">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditando(d);
                    }}
                    title={es.alias.editar}
                    aria-label={es.alias.editar}
                    className="rounded-md px-1.5 py-0.5 text-slate-500 hover:bg-slate-700 hover:text-slate-200"
                  >
                    ✏️
                  </button>
                </td>
              </tr>
            ))}
            {visibles.length === 0 && (
              <tr>
                <td colSpan={6} className="px-2 py-6 text-center text-slate-500">
                  {es.dispositivos.vacio}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {guardar.isError && (
        <p className="mb-3 text-sm text-rose-400">
          {guardar.error instanceof Error ? guardar.error.message : ""}
        </p>
      )}
      {guardar.isSuccess && !hayCambios && !confirmando && (
        <p className="mb-3 text-sm text-emerald-400">{t.hecho}</p>
      )}

      <button
        onClick={() => setConfirmando(true)}
        disabled={!hayCambios}
        className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
      >
        {t.guardarWhitelist}
      </button>

      <Confirmar
        abierto={confirmando}
        titulo={t.tituloWhitelist}
        peligro={false}
        ocupado={guardar.isPending}
        onCancelar={() => setConfirmando(false)}
        onConfirmar={() =>
          guardar.mutate(
            { macs: [...seleccion] },
            {
              onSettled: () => setConfirmando(false),
              onSuccess: () => setMarcadas(null),
            },
          )
        }
      >
        {t.msjWhitelist(seleccion.size)}
      </Confirmar>

      <EditarAlias dispositivo={editando} onCerrar={() => setEditando(null)} />
    </div>
  );
}

function Afectados() {
  const { data } = useAfectados();
  const [editando, setEditando] = useState<FilaWhitelist | null>(null);
  if (!data?.hay_corte) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-slate-400">
          🚫 {t.afectados}
        </span>
        <span className="text-xs text-slate-500">
          {t.afectadosResumen(data.total, data.intentando)}
        </span>
      </div>
      <p className={data.en_curso
        ? "mb-1 text-xs text-rose-300" : "mb-1 text-xs text-slate-500"}>
        {data.en_curso ? t.afectadosEnCurso : t.afectadosFuera}
      </p>
      <p className="mb-3 text-xs text-slate-600">
        {data.registra_intentos ? t.intentosAyuda : t.sinRegistro}
      </p>

      {data.dispositivos.length === 0 ? (
        <p className="text-sm text-emerald-400">{t.sinAfectados}</p>
      ) : (
        <ul className="max-h-96 divide-y divide-slate-800/70 overflow-y-auto rounded-lg border border-slate-800">
          {data.dispositivos.map((d) => (
            <li key={d.mac} className="flex items-center gap-3 px-3 py-1.5 text-sm">
              <div className="min-w-0 flex-1">
                <div className="truncate text-slate-200" title={d.nombre}>
                  {d.nombre}
                </div>
                <div className="font-mono text-xs text-cyan-300/80">{d.ip}</div>
              </div>
              <span className={
                d.intento_hace_s !== null
                  ? "whitespace-nowrap rounded-full bg-rose-500/15 px-2 py-0.5 text-xs text-rose-300"
                  : "whitespace-nowrap text-xs text-slate-600"
              }>
                {d.intento_hace_s !== null
                  ? t.intentoHace(d.intento_hace_s) : t.sinIntentos}
              </span>
              <button
                onClick={() => setEditando({ ...d, en_red: true })}
                title={es.alias.editar}
                aria-label={es.alias.editar}
                className="rounded-md px-1.5 py-0.5 text-slate-500 hover:bg-slate-700 hover:text-slate-200"
              >
                ✏️
              </button>
            </li>
          ))}
        </ul>
      )}

      <EditarAlias dispositivo={editando} onCerrar={() => setEditando(null)} />
    </div>
  );
}

function Eliminar() {
  const { data } = useHorario();
  const eliminar = useEliminarHorario();
  const [confirmando, setConfirmando] = useState(false);

  if (!data?.corte) return null;

  return (
    <div className="rounded-xl border border-rose-950 bg-rose-950/20 p-4">
      <button
        onClick={() => setConfirmando(true)}
        className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-500"
      >
        ⚠️ {t.eliminar}
      </button>
      <Confirmar
        abierto={confirmando}
        titulo={t.tituloEliminar}
        ocupado={eliminar.isPending}
        onCancelar={() => setConfirmando(false)}
        onConfirmar={() =>
          eliminar.mutate({}, { onSettled: () => setConfirmando(false) })
        }
      >
        {t.msjEliminar}
      </Confirmar>
    </div>
  );
}

export function Horario() {
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-slate-100">{t.titulo}</h1>
      <div className="grid items-start gap-4 xl:grid-cols-5">
        <div className="space-y-4 xl:col-span-2">
          <EstadoCorte />
          <Editor />
          <Eliminar />
          <Afectados />
        </div>
        <div className="xl:col-span-3">
          <ListaBlanca />
        </div>
      </div>
    </div>
  );
}
