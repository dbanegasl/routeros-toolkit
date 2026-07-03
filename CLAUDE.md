# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python toolkit for administering a MikroTik RouterOS router (hEX lite, RouterOS v6.49.19) over its native binary API on port 8728. The CLI (`lib/`, `core/`, `scripts/`, `menu.py`, `tests/`) has **no external dependencies** — Python 3.6+ standard library only (tests use `unittest`); there is no build step or linter. The web panel (`backend/` FastAPI + `frontend/` nginx, run via `docker compose`) keeps its dependencies isolated in `backend/requirements.txt` and the Docker images — never add web deps to the CLI layers. Code, comments, and all user-facing output are in **Spanish**; keep new code consistent with that.

**Scripts talk to a live production router.** Anything beyond `print` commands (firewall rules, mangle, queues, schedulers, DHCP leases) mutates real router state. Read-only scripts (`sys_validar`, `info_*`, `mon_*`, `mant_log`, `scan_dispositivos`, `qos_diagnostico`, `qos_monitor`, and `mant_respaldo` without `--full`) are safe to run; be deliberate with `mant_bloqueo`, `horario_internet`, `qos_desplegar`, and `qos_reset`. `mant_respaldo.py` writes local JSON snapshots to `backups/` (gitignored); `--full` additionally creates a `.backup` file on the router.

## Running

```bash
python3 menu.py                          # interactive menu (main entry point)
python3 scripts/info_dispositivos.py     # any script runs standalone, from repo root
python3 scripts/sys_validar.py           # pre-flight connectivity/config check
python3 -m unittest discover -s tests -v # test suite (no router needed)

# Web panel (needs APP_PASSWORD_HASH in config.env — backend/generar_hash.py):
docker compose up -d                     # panel at http://<host>:${PANEL_PORT:-8080}
backend/.venv/bin/python -m pytest backend/tests -q  # backend tests (FakeAPI, no router)
```

Run the tests after touching `lib/` or the QoS rule builders — they pin the protocol encoding and the exact default QoS plan.

Credentials come from `config.env` (gitignored; template in `config.env.example`). `load_config()` in `lib/mikrotik_api.py` resolves them: explicit path → `MIKROTIK_ENV_FILE` → `config.env` at repo root; `MIKROTIK_HOST/PORT/USER/PASSWORD` env vars override the file.

## Architecture

- **`lib/mikrotik_api.py`** — everything shared:
  - `MikroTikAPI`: from-scratch implementation of the RouterOS binary protocol (length-prefixed words, sentences, `!re`/`!done`/`!trap` responses, modern + MD5-challenge login). `command()` returns a list of dicts; `command_raw()` returns raw sentences for config-style commands. Use as a context manager.
  - Helpers: `fmt_speed`/`fmt_bytes`, `is_random_mac` (private MAC detection), `get_mac_vendor_cache` (offline OUI→vendor table), `lookup_mac_vendor_online` (macvendors.com, ~1 req/s rate limit), `resolve_device_name` (hostname → vendor+MAC → MAC fallback), `build_device_map`/`build_name_map` (DHCP+ARP inventory, keyed by IP or MAC), `load_oui_cache`/`save_oui_cache`, `print_header`, `parse_router_date`/`get_router_datetime` (router clock, handles v6 `jul/02/2026` and v7 date formats), `LAN_PREFIX`, and `C` (ANSI colors). Scripts must use these instead of reimplementing them.
  - Tests live in `tests/` (unittest, stdlib only, no router needed): `python3 -m unittest discover -s tests -v`.
- **`lib/app_config.py`** — JSON config files in `config/` (overridable via `MIKROTIK_CONFIG_DIR`, used by tests): `load_json_config`/`save_json_config` with shallow default-merge and clean `ConfigError` on corrupt JSON. Real files are gitignored; `.example` templates are committed. Current files: `config/qos.json` (QoS deploy settings) and `config/whitelist.json` (persistent internet-schedule whitelist).
  - All values from `command()` are **strings** (RouterOS returns text); cast to `int()` for byte counters etc.
- **Error handling**: every script ends with `run_script(main)` (from lib) instead of calling `main()` directly. It maps exceptions to clean Spanish messages with hints (never tracebacks) and fixed exit codes: 0 OK, 1 connection/login, 2 RouterOS-trap/config, 130 Ctrl+C. The lib raises typed exceptions (`MikroTikConnectionError` for login, `MikroTikCommandError` for `!trap`/`!fatal`), both subclasses of RuntimeError. Don't add per-script try/except around the main body. Timeout is configurable via `MIKROTIK_TIMEOUT` in config.env.
- **`menu.py`** — interactive menu; launches scripts as subprocesses via the `MENU` dict (key → script + args). Menu numbers are grouped by decade (first digit = section: 1–9 info, 10s monitoreo, 20s mantenimiento, 30s identificación, 40s horario, 50s QoS, 90s sistema); new options take the next free number in their decade. New scripts should be registered there. Options that mutate the router immediately on launch (the script itself doesn't re-ask) must also go in the `CONFIRMAR` dict so the menu asks for explicit confirmation first (currently 43 = remove schedule, 51 = deploy QoS, 54 = reset QoS); `tests/test_menu.py` pins this invariant.
- **`core/`** — business logic extracted from the scripts (stdlib only, like `lib/`): `dispositivos.py` (inventory/scan/classification), `monitoreo.py` (consumption, interfaces, system, log), `bloqueos.py`, `horario.py` (schedule rules + persistent whitelist), `qos.py` (plan builders + deploy/reset/diagnostic operations), `respaldo.py` (snapshot + router backup). Modules take an already-connected `MikroTikAPI` and **return data — they never print or prompt**; presentation (ANSI tables, dialogs) stays in `scripts/`. New logic goes here so the CLI and the future web backend share one source (see `PLAN_FRONTEND.md`).
- **`scripts/<sección>_*.py`** — standalone scripts named by section prefix (`info_`, `mon_`, `mant_`, `scan_`, `horario_`, `qos_`, `sys_`), one task each: thin CLI presentation over `core/`. Each does `sys.path.insert` to import from `lib`/`core` (repo root + `from lib import ...` / `from core.<módulo> import ...`). Scripts follow argparse + ANSI-colored output conventions; copy an existing script's structure when adding one.
- **`lib/oui_cache.json`** — persisted cache of macvendors.com lookups (written by `scan_dispositivos.py`); committed to the repo.
- **`backend/`** — FastAPI web API over the same `lib/` + `core/` (see `PLAN_FRONTEND.md`). `app/auth.py`: login against `APP_PASSWORD_HASH` (PBKDF2, stdlib; generate with `backend/generar_hash.py`), in-memory httpOnly-cookie sessions, 5/min login rate-limit — the router password never reaches the browser. `app/deps.py`: `get_api` dependency opens one router connection per request under a **global lock** (never parallel connections to the hEX lite). `app/routers/` mirrors `core/` sections; all routes require the session dependency except `/api/auth/*` and `/api/salud` (healthcheck). `app/ws.py`: `/ws/monitor` and `/ws/log` — one shared sampling loop per stream (`Muestreador`): first client starts it, last stops it, all get the same snapshot; persistent router connection under the same global lock; invalid session closes with code 4401; sampling interval via `APP_WS_INTERVALO` (tests set it tiny and monkeypatch `ws.crear_api` to inject the FakeAPI). Exceptions map like CLI exit codes: `MikroTikConnectionError`/`OSError` → 502, `MikroTikCommandError` → 400, Spanish detail + `sugerencia`. Tests in `backend/tests/` (pytest + FakeAPI injected via `dependency_overrides`; venv at `backend/.venv`, gitignored).
- **`frontend/`** — React 18 + Vite + TypeScript strict SPA, served by nginx which also proxies `/api` and `/ws` to the `api` service. TanStack Query for data (`src/api/hooks.ts` — polling reads; 401 flips the `sesion` query so the app falls back to Login), Tailwind CSS v4 dark theme, **all user-facing texts live in `src/i18n/es.ts`** — never hardcode strings in components. `src/lib/formato.ts` mirrors `fmt_bytes`/`fmt_speed` from `lib/` exactly (vitest pins parity). Multi-stage Dockerfile (node build → nginx). Dev: `npm run dev` proxies to uvicorn on :8000; `npm run build` runs `tsc -b` first (type errors fail the build); `npm run test` = vitest.
- **`docker-compose.yml`** — 2 services: `api` (no published port) and `web` (single exposed port, `PANEL_PORT` in `.env`, default 8080). `config.env` is passed via `env_file` (includes `APP_PASSWORD_HASH`); `config/` and `backups/` are volumes shared with the CLI. Backend Dockerfile builds from the **repo root** context (needs `lib/` + `core/`).
- **`index.md`** — technical reference for the RouterOS API protocol.
- **`temp/`** — scratch design docs, not part of the toolkit.

## Documentation map

- **`README.md`** — project overview, quick start, full script table, and the documentation index. Entry point for humans.
- **`index.md`** — complete technical reference: per-script usage with all flags, RouterOS API protocol details, connection-tracking fields.
- **`scripts/README_QOS.md`** — QoS suite overview (`qos_*.py`) and typical deploy→diagnose→monitor→reset flow.
- **`scripts/QOS_USAGE.md`** — detailed QoS deployment manual with troubleshooting; **`scripts/QOS_QUICK_REFERENCE.md`** — QoS traffic classes/priorities cheat sheet.
- **`QOS_IMPLEMENTATION_SUMMARY.txt`** — historical record of the QoS implementation.

When adding or changing a script, update **three places**: the script's docstring, its entry in `index.md` (flags table), and the `MENU` dict in `menu.py`. If the script count or menu options change, the README table and menu option count in `index.md` go stale — update those too.

## Domain knowledge that isn't obvious from any single file

- **FastTrack skips mangle/queues**: real per-connection byte counts require summing `orig-bytes + orig-fasttrack-bytes` (and the `repl-` equivalents). The QoS deploy script disables FastTrack for this reason.
- **QoS suite (`qos_*.py`)** deploys/diagnoses/monitors/resets a Mangle + Queue Tree setup that prioritizes one host (configured in `config/qos.json`; default "Kevin", 192.168.5.22, MAC F0:2F:74:CB:97:3F). Flow: deploy → diagnose → monitor → reset if broken. `qos_desplegar.py --dry-run` prints every rule without touching the router. Rule/queue tables are pure functions (`build_mangle_rules`/`build_queue_tree` in `core/qos.py`) covered by tests; bandwidth limits scale from the configured Mbps (defaults = 100 Mbps = original plan). `qos_reset.py` only removes QoS-tagged items (comments `QoS *`, queues `QoS_*/DL-*/UL-*`) and re-enables FastTrack.
- **RouterOS v6.49.19 caveat**: Queue Tree does not reliably limit bridge-local (LAN-to-LAN) traffic on this version.
- **Internet scheduling (`horario_internet.py`)** uses tagged firewall rules (`HORARIO-INTERNET`/`HORARIO-PERMITIDO`); `mant_bloqueo.py` blocks by IP (`BLOQUEADO-POR-MENU-*`). Both only manage their own rules — preserve that pattern when touching firewall code. Its whitelist persists in `config/whitelist.json` and survives `--remove`; it re-applies when a new schedule is created.
- **LAN subnet is detected, not hardcoded**: `get_lan_prefix(api)` reads `/ip/address` (bridge interface preferred), with `MIKROTIK_LAN_PREFIX` env override and `LAN_PREFIX` ("192.168.") as fallback. Don't add new `192.168.` literals.
