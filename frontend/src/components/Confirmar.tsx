/**
 * Confirmar — diálogo estándar para toda acción ⚠️ que modifica el
 * router (el espejo del dict CONFIRMAR del menú CLI). El botón de
 * confirmar siempre exige un clic explícito; Escape o el fondo cancelan.
 */
import type { ReactNode } from "react";

import { es } from "../i18n/es";

interface Props {
  abierto: boolean;
  titulo: string;
  peligro?: boolean;
  ocupado?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
  children: ReactNode;
}

export function Confirmar({
  abierto, titulo, peligro = true, ocupado = false,
  onConfirmar, onCancelar, children,
}: Props) {
  if (!abierto) return null;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
      onClick={onCancelar}
      onKeyDown={(e) => e.key === "Escape" && onCancelar()}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-2 flex items-center gap-2 text-lg font-semibold text-slate-100">
          ⚠️ {titulo}
        </h2>
        <div className="mb-6 text-sm text-slate-300">{children}</div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancelar}
            disabled={ocupado}
            className="rounded-lg px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            {es.confirmar.cancelar}
          </button>
          <button
            onClick={onConfirmar}
            disabled={ocupado}
            className={[
              "rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50",
              peligro ? "bg-rose-600 hover:bg-rose-500"
                      : "bg-sky-600 hover:bg-sky-500",
            ].join(" ")}
          >
            {ocupado ? es.confirmar.aplicando : es.confirmar.confirmar}
          </button>
        </div>
      </div>
    </div>
  );
}
