/**
 * Horario — corte de internet por horario ⚠️
 * Estado del corte, editor (crear/reemplazar), lista blanca con toggles
 * y eliminación. Toda escritura pasa por el diálogo Confirmar.
 */
import { useEffect, useMemo, useState } from "react";

import {
  useCrearHorario,
  useDispositivos,
  useEliminarHorario,
  useGuardarWhitelist,
  useHorario,
  useWhitelist,
} from "../api/hooks";
import { Confirmar } from "../components/Confirmar";
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
  ip: string | null;
  en_red: boolean;
}

function ListaBlanca() {
  const whitelist = useWhitelist();
  const red = useDispositivos();
  const guardar = useGuardarWhitelist();
  const [marcadas, setMarcadas] = useState<Set<string> | null>(null);
  const [confirmando, setConfirmando] = useState(false);

  // Filas: todos los dispositivos de la red ∪ whitelist (los offline
  // también, para poder quitarlos), como el --allow del CLI.
  const filas = useMemo<FilaWhitelist[]>(() => {
    const porMac = new Map<string, FilaWhitelist>();
    for (const d of red.data?.dispositivos ?? []) {
      if (!d.mac) continue;
      porMac.set(d.mac.toUpperCase(), {
        mac: d.mac.toUpperCase(),
        nombre: d.nombre,
        ip: d.ip,
        en_red: true,
      });
    }
    for (const w of whitelist.data?.dispositivos ?? []) {
      if (!porMac.has(w.mac)) {
        porMac.set(w.mac, {
          mac: w.mac,
          nombre: w.nombre,
          ip: w.ip,
          en_red: w.en_red,
        });
      }
    }
    return [...porMac.values()].sort((a, b) =>
      (a.ip ?? "z").localeCompare(b.ip ?? "z", "es", { numeric: true }),
    );
  }, [red.data, whitelist.data]);

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
      <div className="mb-1 text-sm font-medium text-slate-400">
        🛡️ {t.whitelist}
      </div>
      <p className="mb-3 text-xs text-slate-500">{t.whitelistAyuda}</p>

      <div className="mb-4 max-h-80 space-y-1 overflow-y-auto">
        {filas.map((d) => (
          <label
            key={d.mac}
            className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-800/60"
          >
            <input
              type="checkbox"
              checked={seleccion.has(d.mac)}
              onChange={() => toggle(d.mac)}
              className="accent-emerald-500"
            />
            <span className="flex-1 truncate text-slate-200">
              {d.nombre || d.mac}
            </span>
            <span className="font-mono text-xs text-slate-600">{d.mac}</span>
            <span
              className={
                d.en_red
                  ? "text-xs text-emerald-400"
                  : "text-xs text-slate-600"
              }
            >
              {d.en_red ? `● ${t.enRed}` : t.offline}
            </span>
          </label>
        ))}
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
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <EstadoCorte />
          <Editor />
          <Eliminar />
        </div>
        <ListaBlanca />
      </div>
    </div>
  );
}
