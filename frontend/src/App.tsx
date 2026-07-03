import { Navigate, Route, Routes } from "react-router-dom";

import { useSesion } from "./api/hooks";
import { Layout } from "./components/Layout";
import { es } from "./i18n/es";
import { Dashboard } from "./pages/Dashboard";
import { Dispositivos } from "./pages/Dispositivos";
import { Login } from "./pages/Login";

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
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/dispositivos" element={<Dispositivos />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
