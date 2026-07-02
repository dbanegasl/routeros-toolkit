# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Python toolkit for administering a MikroTik RouterOS router (hEX lite, RouterOS v6.49.19) over its native binary API on port 8728. **No external dependencies** — Python 3.6+ standard library only (including the tests, which use `unittest`). There is no build step or linter. Code, comments, and all user-facing output are in **Spanish**; keep new code consistent with that.

**Scripts talk to a live production router.** Anything beyond `print` commands (firewall rules, mangle, queues, schedulers, DHCP leases) mutates real router state. Read-only scripts (01–05, 07, 08, 00, 11, 12, and 14 without `--full`) are safe to run; be deliberate with 06, 09, 10, and 13. `14_backup.py` writes local JSON snapshots to `backups/` (gitignored); `--full` additionally creates a `.backup` file on the router.

## Running

```bash
python3 menu.py                          # interactive menu (main entry point)
python3 scripts/01_list_devices.py       # any script runs standalone, from repo root
python3 scripts/00_validate_router.py    # pre-flight connectivity/config check
python3 -m unittest discover -s tests -v # test suite (no router needed)
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
- **`menu.py`** — interactive menu; launches scripts as subprocesses via the `MENU` dict (key → script + args). New scripts should be registered there. Options that mutate the router immediately on launch (the script itself doesn't re-ask) must also go in the `CONFIRMAR` dict so the menu asks for explicit confirmation first (currently 23 = deploy QoS, 26 = reset QoS); `tests/test_menu.py` pins this invariant.
- **`scripts/NN_*.py`** — numbered standalone scripts, one task each. Each does `sys.path.insert` to import from `lib` (most add the repo root and use `from lib import ...`). Scripts follow argparse + ANSI-colored output conventions; copy an existing script's structure when adding one.
- **`lib/oui_cache.json`** — persisted cache of macvendors.com lookups (written by `08_scan_devices.py`); committed to the repo.
- **`index.md`** — technical reference for the RouterOS API protocol.
- **`temp/`** — scratch design docs, not part of the toolkit.

## Documentation map

- **`README.md`** — project overview, quick start, full script table, and the documentation index. Entry point for humans.
- **`index.md`** — complete technical reference: per-script usage with all flags (00–09), RouterOS API protocol details, connection-tracking fields.
- **`scripts/README_QOS.md`** — QoS suite overview (scripts 10–13) and typical deploy→diagnose→monitor→reset flow.
- **`scripts/10_USAGE.md`** — detailed QoS deployment manual with troubleshooting; **`scripts/10_QUICK_REFERENCE.md`** — QoS traffic classes/priorities cheat sheet.
- **`QOS_IMPLEMENTATION_SUMMARY.txt`** — historical record of the QoS implementation.

When adding or changing a script, update **three places**: the script's docstring, its entry in `index.md` (flags table), and the `MENU` dict in `menu.py`. If the script count or menu options change, the README table and menu option count in `index.md` go stale — update those too.

## Domain knowledge that isn't obvious from any single file

- **FastTrack skips mangle/queues**: real per-connection byte counts require summing `orig-bytes + orig-fasttrack-bytes` (and the `repl-` equivalents). The QoS deploy script disables FastTrack for this reason.
- **QoS suite (scripts 10–13)** deploys/diagnoses/monitors/resets a Mangle + Queue Tree setup that prioritizes one host (configured in `config/qos.json`; default "Kevin", 192.168.5.22, MAC F0:2F:74:CB:97:3F). Flow: deploy → diagnose → monitor → reset if broken. `10_deploy_qos.py --dry-run` prints every rule without touching the router. Rule/queue tables are pure functions (`build_mangle_rules`/`build_queue_tree`) covered by tests; bandwidth limits scale from the configured Mbps (defaults = 100 Mbps = original plan). `13_reset_qos.py` only removes QoS-tagged items (comments `QoS *`, queues `QoS_*/DL-*/UL-*`) and re-enables FastTrack.
- **RouterOS v6.49.19 caveat**: Queue Tree does not reliably limit bridge-local (LAN-to-LAN) traffic on this version.
- **Internet scheduling (script 09)** uses tagged firewall rules (`HORARIO-INTERNET`/`HORARIO-PERMITIDO`); `06_block_ip.py` blocks by IP (`BLOQUEADO-POR-MENU-*`). Both only manage their own rules — preserve that pattern when touching firewall code. The 09 whitelist persists in `config/whitelist.json` and survives `--remove`; it re-applies when a new schedule is created.
- **LAN subnet is detected, not hardcoded**: `get_lan_prefix(api)` reads `/ip/address` (bridge interface preferred), with `MIKROTIK_LAN_PREFIX` env override and `LAN_PREFIX` ("192.168.") as fallback. Don't add new `192.168.` literals.
