import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useSesion } from "./api/hooks";
import { Layout } from "./components/Layout";
import { es } from "./i18n/es";
import { Dashboard } from "./pages/Dashboard";
import { Dispositivos } from "./pages/Dispositivos";
import { Login } from "./pages/Login";

// Carga diferida: recharts solo se descarga al entrar a estas páginas
const Monitoreo = lazy(() =>
  import("./pages/Monitoreo").then((m) => ({ default: m.Monitoreo })),
);
const Log = lazy(() =>
  import("./pages/Log").then((m) => ({ default: m.Log })),
);
const Horario = lazy(() =>
  import("./pages/Horario").then((m) => ({ default: m.Horario })),
);

export default function App() {
  const sesion = useSesion();

  if (sesion.isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center bg-slate-950 text-slate-400">
        {es.errores.cargando}
      </div>
    );
  }

  if (!sesion.data?.autenticada) {
    return <Login />;
  }

  return (
    <Layout>
      <Suspense
        fallback={
          <div className="py-12 text-center text-sm text-slate-500">
            {es.errores.cargando}
          </div>
        }
      >
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/dispositivos" element={<Dispositivos />} />
          <Route path="/monitoreo" element={<Monitoreo />} />
          <Route path="/horario" element={<Horario />} />
          <Route path="/log" element={<Log />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
