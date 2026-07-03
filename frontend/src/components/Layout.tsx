/**
 * Layout — navegación responsive: barra lateral en escritorio,
 * barra inferior en el celular (el caso de uso principal).
 */
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useLogout } from "../api/hooks";
import { es } from "../i18n/es";

const enlaces = [
  { a: "/", texto: es.nav.dashboard, icono: "🏠" },
  { a: "/dispositivos", texto: es.nav.dispositivos, icono: "📱" },
  { a: "/monitoreo", texto: es.nav.monitoreo, icono: "📈" },
  { a: "/horario", texto: es.nav.horario, icono: "⏰" },
  { a: "/qos", texto: es.nav.qos, icono: "⚡" },
  { a: "/log", texto: es.nav.log, icono: "📜" },
  { a: "/respaldos", texto: es.nav.respaldos, icono: "💾" },
];

function clasesEnlace(activo: boolean): string {
  return [
    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
    activo
      ? "bg-sky-500/15 text-sky-300"
      : "text-slate-400 hover:bg-slate-800 hover:text-slate-200",
  ].join(" ");
}

export function Layout({ children }: { children: ReactNode }) {
  const logout = useLogout();

  return (
    <div className="min-h-dvh bg-slate-950 text-slate-200">
      {/* Barra lateral (≥ md) */}
      <aside className="fixed inset-y-0 left-0 hidden w-52 flex-col border-r border-slate-800 bg-slate-900/60 p-4 md:flex">
        <div className="mb-6 px-2">
          <div className="text-lg font-semibold">🌐 {es.app.titulo}</div>
          <div className="text-xs text-slate-500">{es.app.subtitulo}</div>
        </div>
        <nav className="flex flex-col gap-1">
          {enlaces.map((e) => (
            <NavLink key={e.a} to={e.a} end={e.a === "/"}
              className={({ isActive }) => clasesEnlace(isActive)}>
              <span>{e.icono}</span> {e.texto}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={() => logout.mutate()}
          className="mt-auto flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-200"
        >
          🚪 {es.nav.salir}
        </button>
      </aside>

      {/* Encabezado móvil */}
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800 bg-slate-950/90 px-4 py-3 backdrop-blur md:hidden">
        <span className="font-semibold">🌐 {es.app.titulo}</span>
        <button onClick={() => logout.mutate()}
          className="text-sm text-slate-400">
          {es.nav.salir}
        </button>
      </header>

      <main className="px-4 py-6 pb-24 md:ml-52 md:pb-6 lg:px-8">
        <div className="mx-auto max-w-5xl">{children}</div>
      </main>

      {/* Barra inferior móvil */}
      <nav className="fixed inset-x-0 bottom-0 z-10 flex border-t border-slate-800 bg-slate-900/95 backdrop-blur md:hidden">
        {enlaces.map((e) => (
          <NavLink key={e.a} to={e.a} end={e.a === "/"}
            className={({ isActive }) =>
              [
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-xs",
                isActive ? "text-sky-300" : "text-slate-500",
              ].join(" ")
            }>
            <span className="text-lg">{e.icono}</span>
            {e.texto}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
