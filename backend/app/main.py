"""
main.py — Aplicación FastAPI del RouterOS Toolkit
=================================================

Panel web del toolkit (Fase 1: auth + lecturas). Los errores del router
se mapean a HTTP con el mismo criterio que los exit codes del CLI:
    MikroTikConnectionError → 502  (conexión/login al router)
    MikroTikCommandError    → 400  (!trap / configuración)
Mensajes en español con sugerencia, nunca tracebacks.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lib import MikroTikConnectionError, MikroTikCommandError
from . import auth
from .routers import dispositivos, horario, monitoreo, sistema

app = FastAPI(
    title="RouterOS Toolkit — Panel web",
    description="API del panel de administración del MikroTik hEX lite. "
                "Inicia sesión en /api/auth/login para usar los endpoints.",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.include_router(auth.router)
app.include_router(sistema.salud_router)
app.include_router(sistema.router)
app.include_router(dispositivos.router)
app.include_router(monitoreo.router)
app.include_router(horario.router)


@app.exception_handler(MikroTikConnectionError)
def error_conexion(request: Request, exc: MikroTikConnectionError):
    return JSONResponse(status_code=502, content={
        "detail": f"No se pudo conectar al router: {exc}",
        "sugerencia": "Verifica que el router esté encendido, que el "
                      "servicio API (8728) esté habilitado y que las "
                      "credenciales de config.env sean correctas.",
    })


@app.exception_handler(MikroTikCommandError)
def error_comando(request: Request, exc: MikroTikCommandError):
    return JSONResponse(status_code=400, content={
        "detail": f"El router rechazó el comando: {exc}",
        "sugerencia": "Revisa la configuración enviada; el detalle viene "
                      "del propio RouterOS.",
    })


@app.exception_handler(OSError)
def error_red(request: Request, exc: OSError):
    return JSONResponse(status_code=502, content={
        "detail": f"Error de red hablando con el router: {exc}",
        "sugerencia": "¿El equipo donde corre el panel alcanza la IP del "
                      "router? Prueba: ping al router desde ese equipo.",
    })
