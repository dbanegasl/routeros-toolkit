/**
 * EditarAlias — modal para poner, cambiar o quitar el alias de una MAC.
 * El alias vive en config/alias.json (no toca el router), así que no
 * pasa por el diálogo Confirmar. Enter guarda; Escape o el fondo cancelan.
 */
import { useEffect, useState } from "react";

import { useGuardarAlias } from "../api/hooks";
import { es } from "../i18n/es";

const t = es.alias;
const ALIAS_MAX = 40; // espejo de lib.app_config.ALIAS_MAX

export interface DispositivoAlias {
  mac: string;
  ip: string | null;
  alias: string;
  nombre_detectado: string;
}

interface Props {
  dispositivo: DispositivoAlias | null;
  onCerrar: () => void;
}

export function EditarAlias({ dispositivo, onCerrar }: Props) {
  const guardar = useGuardarAlias();
  const [valor, setValor] = useState("");

  // Reiniciar el formulario cada vez que se abre para otro dispositivo
  const { reset } = guardar;
  useEffect(() => {
    setValor(dispositivo?.alias ?? "");
    reset();
  }, [dispositivo?.mac, dispositivo?.alias, reset]);

  if (!dispositivo) return null;

  function enviar(alias: string) {
    if (!dispositivo) return;
    guardar.mutate(
      { mac: dispositivo.mac, alias: alias.trim() },
      { onSuccess: onCerrar },
    );
  }

  const sinCambios = valor.trim() === dispositivo.alias;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
      onClick={onCerrar}
      onKeyDown={(e) => e.key === "Escape" && onCerrar()}
    >
      <form
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          if (!sinCambios) enviar(valor);
        }}
      >
        <h2 className="mb-1 text-lg font-semibold text-slate-100">
          ✏️ {t.titulo}
        </h2>
        <p className="mb-4 text-xs text-slate-500">{t.ayuda}</p>

        <dl className="mb-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-slate-500">{t.detectado}</dt>
          <dd className="truncate text-slate-200">
            {dispositivo.nombre_detectado || "—"}
          </dd>
          <dt className="text-slate-500">{t.mac}</dt>
          <dd className="font-mono text-xs leading-5 text-slate-400">
            {dispositivo.mac}
          </dd>
          <dt className="text-slate-500">{t.ip}</dt>
          <dd className="font-mono text-xs leading-5 text-cyan-300">
            {dispositivo.ip ?? <span className="text-slate-600">{t.sinIp}</span>}
          </dd>
        </dl>

        <label className="mb-1 block text-sm text-slate-300" htmlFor="alias">
          {t.campo}
        </label>
        <input
          id="alias"
          autoFocus
          value={valor}
          maxLength={ALIAS_MAX}
          onChange={(e) => setValor(e.target.value)}
          placeholder={t.placeholder(dispositivo.nombre_detectado)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-sky-500"
        />
        <div className="mt-1 text-right text-xs text-slate-600">
          {valor.length}/{ALIAS_MAX}
        </div>

        {guardar.isError && (
          <p className="mt-2 text-sm text-rose-400">
            {guardar.error instanceof Error ? guardar.error.message : ""}
          </p>
        )}

        <div className="mt-5 flex items-center gap-3">
          {dispositivo.alias && (
            <button
              type="button"
              onClick={() => enviar("")}
              disabled={guardar.isPending}
              className="rounded-lg px-3 py-2 text-sm text-rose-300 hover:bg-rose-950/40 disabled:opacity-50"
            >
              {t.quitar}
            </button>
          )}
          <div className="ml-auto flex gap-3">
            <button
              type="button"
              onClick={onCerrar}
              disabled={guardar.isPending}
              className="rounded-lg px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              {es.confirmar.cancelar}
            </button>
            <button
              type="submit"
              disabled={guardar.isPending || sinCambios}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {guardar.isPending ? t.guardando : t.guardar}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
