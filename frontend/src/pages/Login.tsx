import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { useLogin } from "../api/hooks";
import { es } from "../i18n/es";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return es.login.errorPassword;
    if (error.status === 429) return es.login.errorRateLimit;
  }
  return es.login.errorServidor;
}

export function Login() {
  const [password, setPassword] = useState("");
  const login = useLogin();

  function enviar(e: FormEvent) {
    e.preventDefault();
    if (password) login.mutate(password);
  }

  return (
    <div className="grid min-h-dvh place-items-center bg-slate-950 px-4">
      <form onSubmit={enviar}
        className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/60 p-8">
        <div className="mb-6 text-center">
          <div className="text-4xl">🌐</div>
          <h1 className="mt-2 text-xl font-semibold text-slate-100">
            {es.login.titulo}
          </h1>
          <p className="mt-1 text-sm text-slate-500">{es.login.instruccion}</p>
        </div>

        <input
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={es.login.placeholder}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2.5 text-slate-100 placeholder-slate-600 outline-none focus:border-sky-500"
        />

        {login.isError && (
          <p className="mt-3 text-sm text-rose-400">
            {mensajeError(login.error)}
          </p>
        )}

        <button
          type="submit"
          disabled={login.isPending || !password}
          className="mt-4 w-full rounded-lg bg-sky-600 py-2.5 font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-50"
        >
          {login.isPending ? es.login.entrando : es.login.entrar}
        </button>
      </form>
    </div>
  );
}
