"""
mikrotik_api.py — Librería cliente para RouterOS API (puerto 8728)
===================================================================

Protocolo:
    MikroTik expone su propia API binaria en el puerto TCP 8728 (sin TLS)
    y 8729 (con TLS). El protocolo consiste en "sentences" (oraciones), donde
    cada sentence contiene una lista de "words" (palabras):

        Sentence = [Word1, Word2, ..., WordN, b'\\x00']  (terminador = byte 0)

    Cada word se prefija con su longitud codificada en 1–4 bytes:
        - longitud < 0x80          → 1 byte
        - longitud < 0x4000        → 2 bytes (MSB = 10)
        - longitud < 0x200000      → 3 bytes (MSB = 110)
        - longitud < 0x10000000    → 4 bytes (MSB = 1110)

    Tipos de words:
        - Comandos:     /ip/dhcp-server/lease/print
        - Atributos:    =nombre=valor
        - Queries:      ?nombre=valor  (filtros)
        - Respuestas:   !re, !done, !trap, !fatal

Autenticación (RouterOS v6):
    El login soporta dos modos:
    1. Moderno (v6.43+):  envía usuario y contraseña directamente en /login
    2. Legacy (MD5):      el router devuelve un challenge, se responde con
                          MD5(\\x00 + password + challenge)

Uso rápido:
    from lib.mikrotik_api import MikroTikAPI, load_config

    cfg = load_config()                   # lee config.env
    with MikroTikAPI(**cfg) as api:
        leases = api.command('/ip/dhcp-server/lease/print')
        for l in leases:
            print(l['address'], l.get('host-name'))
"""

import socket
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Prefijo LAN de respaldo cuando no se puede detectar desde el router.
LAN_PREFIX = "192.168."


# ---------------------------------------------------------------------------
# Excepciones tipadas (subclases de RuntimeError por compatibilidad)
# ---------------------------------------------------------------------------

class MikroTikConnectionError(RuntimeError):
    """Fallo de conexión o autenticación con el router."""


class MikroTikCommandError(RuntimeError):
    """El router rechazó un comando (!trap / !fatal)."""


# ---------------------------------------------------------------------------
# Carga de configuración
# ---------------------------------------------------------------------------

def load_config(env_file: Optional[str] = None) -> dict:
    """
    Lee las credenciales desde un archivo .env.

    Busca en este orden:
        1. Ruta explícita pasada como argumento
        2. Variable de entorno MIKROTIK_ENV_FILE
        3. Archivo config.env en el mismo directorio que este script
        4. Archivo config.env en el directorio padre (raíz del proyecto)

    Retorna un dict con claves: host, port, username, password
    """
    search_paths = []
    if env_file:
        search_paths.append(Path(env_file))
    if os.environ.get("MIKROTIK_ENV_FILE"):
        search_paths.append(Path(os.environ["MIKROTIK_ENV_FILE"]))
    search_paths += [
        Path(__file__).parent.parent / "config.env",
        Path(__file__).parent / "config.env",
    ]

    config = {}
    for path in search_paths:
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    key, _, value = line.partition("=")
                    config[key.strip()] = value.strip()
            break

    # También acepta variables de entorno del sistema operativo (sobreescriben el archivo)
    for env_var, cfg_key in [
        ("MIKROTIK_HOST", "MIKROTIK_HOST"),
        ("MIKROTIK_PORT", "MIKROTIK_PORT"),
        ("MIKROTIK_USER", "MIKROTIK_USER"),
        ("MIKROTIK_PASSWORD", "MIKROTIK_PASSWORD"),
    ]:
        if os.environ.get(env_var):
            config[cfg_key] = os.environ[env_var]

    if os.environ.get("MIKROTIK_TIMEOUT"):
        config["MIKROTIK_TIMEOUT"] = os.environ["MIKROTIK_TIMEOUT"]

    return {
        "host":     config.get("MIKROTIK_HOST", "192.168.5.1"),
        "port":     int(config.get("MIKROTIK_PORT", 8728)),
        "username": config.get("MIKROTIK_USER", "admin"),
        "password": config.get("MIKROTIK_PASSWORD", ""),
        "timeout":  float(config.get("MIKROTIK_TIMEOUT", 15)),
    }


# ---------------------------------------------------------------------------
# Clase principal
# ---------------------------------------------------------------------------

class MikroTikAPI:
    """
    Cliente para el protocolo RouterOS API (puerto 8728).

    Soporta context manager (with):
        with MikroTikAPI(host, username, password) as api:
            results = api.command('/ip/address/print')

    Parámetros:
        host      — IP o hostname del router (default: 192.168.5.1)
        port      — Puerto API (default: 8728, TLS: 8729)
        username  — Usuario RouterOS (default: admin)
        password  — Contraseña RouterOS
        timeout   — Timeout en segundos para operaciones de red (default: 15)
    """

    def __init__(self, host="192.168.5.1", port=8728, username="admin",
                 password="", timeout=15):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------
    # Conexión y autenticación
    # ------------------------------------------------------------------

    def connect(self):
        """Abre la conexión TCP e inicia sesión en el router."""
        self._sock = socket.create_connection((self.host, self.port),
                                              timeout=self.timeout)
        self._sock.settimeout(self.timeout)
        self._login()

    def close(self):
        """Cierra la conexión TCP."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _login(self):
        """
        Inicia sesión usando el método moderno (v6.43+) con fallback a MD5.
        Lanza RuntimeError si las credenciales son incorrectas.
        """
        # Intento 1: envío directo de contraseña (RouterOS ≥ 6.43)
        self._send_sentence(["/login",
                             f"=name={self.username}",
                             f"=password={self.password}"])
        resp = self._recv_sentence()

        # RouterOS < 6.43 responde "!done =ret=<challenge>": la presencia
        # del challenge exige completar el login MD5 aunque venga "!done".
        challenge = None
        for word in resp:
            if word.startswith("=ret="):
                challenge = bytes.fromhex(word[5:])
                break

        if challenge is None:
            if resp and resp[0] == "!done":
                return  # Login moderno exitoso
            raise MikroTikConnectionError(f"Login fallido: {resp}")

        md5 = hashlib.md5()
        md5.update(b"\x00")
        md5.update(self.password.encode("utf-8"))
        md5.update(challenge)
        self._send_sentence(["/login",
                             f"=name={self.username}",
                             f"=response=00{md5.hexdigest()}"])
        resp2 = self._recv_sentence()
        if not resp2 or resp2[0] != "!done":
            raise MikroTikConnectionError(f"Login MD5 fallido: {resp2}")

    # ------------------------------------------------------------------
    # Ejecución de comandos
    # ------------------------------------------------------------------

    def command(self, cmd: str, params: Optional[list] = None,
                queries: Optional[list] = None) -> list:
        """
        Ejecuta un comando RouterOS y retorna una lista de dicts.

        Args:
            cmd     — Comando, ej: '/ip/dhcp-server/lease/print'
            params  — Lista de '=clave=valor' para pasar al comando
            queries — Lista de '?clave=valor' para filtrar resultados

        Returns:
            Lista de diccionarios. Cada dict es un registro (!re).

        Ejemplo:
            api.command('/ip/firewall/connection/print',
                        queries=['?src-address=192.168.5.22'])
        """
        sentence = [cmd]
        if params:
            sentence.extend(params)
        if queries:
            sentence.extend(queries)

        self._send_sentence(sentence)

        results = []
        current: dict = {}

        while True:
            words = self._recv_sentence()
            if not words:
                break
            tag = words[0]

            if tag == "!done":
                if current:
                    results.append(current)
                break
            elif tag == "!re":
                if current:
                    results.append(current)
                current = {}
            elif tag == "!trap":
                error = " | ".join(words[1:])
                raise MikroTikCommandError(f"RouterOS error: {error}")
            elif tag == "!fatal":
                raise MikroTikCommandError(f"RouterOS fatal: {words}")

            for word in words[1:]:
                if word.startswith("=") and "=" in word[1:]:
                    key, _, val = word[1:].partition("=")
                    current[key] = val

        return results

    def command_raw(self, sentence: list) -> list:
        """
        Envía una sentence completa sin procesamiento.
        Útil para comandos de configuración o con sintaxis especial.
        Retorna las sentences de respuesta en crudo como listas de strings.
        """
        self._send_sentence(sentence)
        responses = []
        while True:
            words = self._recv_sentence()
            responses.append(words)
            if not words or words[0] in ("!done", "!fatal"):
                break
        return responses

    # ------------------------------------------------------------------
    # Helpers — protocolo de bajo nivel
    # ------------------------------------------------------------------

    def _send_length(self, length: int):
        """Codifica y envía la longitud de una word según el protocolo RouterOS."""
        if length < 0x80:
            self._sock.sendall(bytes([length]))
        elif length < 0x4000:
            length |= 0x8000
            self._sock.sendall(bytes([(length >> 8) & 0xFF, length & 0xFF]))
        elif length < 0x200000:
            length |= 0xC00000
            self._sock.sendall(bytes([(length >> 16) & 0xFF,
                                       (length >> 8) & 0xFF, length & 0xFF]))
        else:
            length |= 0xE0000000
            self._sock.sendall(bytes([(length >> 24) & 0xFF, (length >> 16) & 0xFF,
                                       (length >> 8) & 0xFF, length & 0xFF]))

    def _recv_length(self) -> int:
        """Lee y decodifica la longitud de la siguiente word."""
        raw = self._sock.recv(1)
        if not raw:
            return 0
        b = raw[0]
        if b & 0x80 == 0:
            return b
        elif b & 0xC0 == 0x80:
            return ((b & 0x3F) << 8) | self._sock.recv(1)[0]
        elif b & 0xE0 == 0xC0:
            r = self._recv_exact(2)
            return ((b & 0x1F) << 16) | (r[0] << 8) | r[1]
        else:
            r = self._recv_exact(3)
            return ((b & 0x0F) << 24) | (r[0] << 16) | (r[1] << 8) | r[2]

    def _recv_exact(self, n: int) -> bytes:
        """Lee exactamente n bytes del socket."""
        data = b""
        while len(data) < n:
            chunk = self._sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Conexión cerrada inesperadamente")
            data += chunk
        return data

    def _send_sentence(self, words: list):
        """Envía una sentence completa (lista de strings + terminador \\x00)."""
        for word in words:
            enc = word.encode("utf-8")
            self._send_length(len(enc))
            self._sock.sendall(enc)
        self._sock.sendall(b"\x00")

    def _recv_sentence(self) -> list:
        """Lee una sentence completa y retorna lista de strings."""
        words = []
        while True:
            length = self._recv_length()
            if length == 0:
                break
            words.append(self._recv_exact(length).decode("utf-8", errors="replace"))
        return words


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------

def fmt_speed(bps: int) -> str:
    """Convierte bytes/segundo a string legible (bps / Kbps / Mbps)."""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    elif bps >= 1_000:
        return f"{bps / 1_000:.1f} Kbps"
    return f"{bps} bps"


def fmt_bytes(b: int) -> str:
    """Convierte bytes a string legible (B / KB / MB / GB)."""
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.2f} GB"
    elif b >= 1_048_576:
        return f"{b / 1_048_576:.2f} MB"
    elif b >= 1_024:
        return f"{b / 1_024:.1f} KB"
    return f"{b} B"


def is_random_mac(mac: str) -> bool:
    """
    Detecta si una MAC es localmente administrada (aleatoria/privada).

    Las MACs aleatorias tienen el bit 1 (segunda posición) del primer octeto en 1.
    Ejemplo: 92:xx → 0x92 = 10010010 → bit 1 encendido → aleatoria.
    iOS 14+, Android 10+, Windows 10+ generan estas MACs por privacidad.
    """
    if not mac or len(mac) < 2:
        return False
    try:
        first_byte = int(mac.replace(":", "").replace("-", "")[:2], 16)
        return bool(first_byte & 0x02)
    except ValueError:
        return False


def get_mac_vendor_cache() -> dict:
    """
    Retorna un dict con prefijos OUI conocidos (sin necesitar internet).
    Clave: primeros 8 caracteres de la MAC en mayúsculas (AA:BB:CC).
    """
    return {
        # Apple
        "00:1E:C2": "Apple",
        "AC:BC:32": "Apple",
        "F0:18:98": "Apple",
        "8C:85:90": "Apple",
        "60:F8:1D": "Apple",
        "A8:86:DD": "Apple",
        "98:10:E8": "Apple",
        "C4:B3:01": "Apple",
        "38:CA:DA": "Apple",
        "00:23:12": "Apple",
        "00:26:BB": "Apple",
        "3C:07:54": "Apple",
        "78:D7:5F": "Apple",
        "F4:F1:5A": "Apple",
        "DC:A4:CA": "Apple",
        "B8:E8:56": "Apple",
        # Computadoras / placas madre
        "F0:2F:74": "ASUSTeK",
        "BC:AE:C5": "ASUSTeK",
        "D8:5E:D3": "GIGABYTE",
        "1C:69:7A": "GIGABYTE",
        "00:90:A9": "Intel",
        "FC:3C:D7": "Foxconn",
        "84:28:59": "Liteon/Realtek",
        "10:BF:67": "Intel",
        "9C:53:22": "Intel",
        "8C:8D:28": "Intel",
        "00:1B:21": "Intel",
        "A4:C3:F0": "Intel",
        # Amazon (Echo, Fire, plugs, Ring, Blink)
        "8C:2A:85": "Amazon",
        "08:7C:39": "Amazon",
        "74:58:F3": "Amazon",
        "08:57:FB": "Amazon",
        "74:AB:93": "Blink (Amazon)",
        "00:F3:61": "Amazon",
        "40:B4:CD": "Amazon",
        "FC:A1:83": "Amazon",
        # TP-Link / Deco
        "DC:62:79": "TP-Link",
        "54:D6:0D": "TP-Link",
        "A8:80:55": "TP-Link",
        "50:D4:F7": "TP-Link",
        "3C:52:A1": "TP-Link",
        # Hikvision / EZVIZ
        "60:DC:81": "EZVIZ/Hikvision",
        "C0:56:E3": "Hikvision",
        # Google / Nest / Chromecast
        "44:07:0B": "Google",
        "F4:F5:D8": "Google",
        "6C:AD:F8": "Google",
        # Samsung
        "64:1C:AE": "Samsung",
        "A6:E5:35": "Samsung",
        "78:AB:BB": "Samsung",
        "8C:C8:4B": "Samsung",
        "50:32:75": "Samsung",
        # Xiaomi / Redmi / POCO
        "F6:4F:F8": "Xiaomi",
        "22:AE:16": "Xiaomi",
        "3A:F9:EE": "Xiaomi",
        "78:11:DC": "Xiaomi",
        "A4:50:46": "Xiaomi",
        "34:CE:00": "Xiaomi",
        # Impresoras
        "B0:E8:92": "Epson",
        "00:26:AB": "Epson",
        "44:D2:44": "HP",
        "3C:D9:2B": "HP",
        "B4:B6:86": "Brother",
        "00:1B:A9": "Brother",
        # Routers / APs genéricos
        "18:D6:C7": "TP-Link",
        "18:A6:F7": "Belkin",
        "C0:C9:E3": "Netgear",
        "C4:E9:84": "Netgear",
        "00:22:B0": "Linksys",
        # IoT / Smart home
        "DC:29:19": "Espressif (IoT)",
        "E8:DB:84": "Espressif (IoT)",
        "30:AE:A4": "Espressif (IoT)",
        "AC:67:B2": "Espressif (IoT)",
        "CC:50:E3": "Espressif (IoT)",
        # Otros
        "38:1F:8D": "Realtek",
        "18:DE:50": "Broadcom",
        "FC:3C:D7": "Foxconn",
    }


def lookup_mac_vendor_online(mac: str, cache: dict, timeout: int = 3) -> str:
    """
    Consulta la API gratuita de macvendors.com para obtener el fabricante.
    Guarda el resultado en `cache` para no repetir la consulta.
    Retorna el nombre del fabricante o cadena vacía si no se encuentra.

    Límite de uso: ~1 req/seg (free tier). Usar solo para OUIs desconocidos.
    """
    import urllib.request
    import time

    oui = mac[:8].upper()
    if oui in cache:
        return cache[oui]

    try:
        url = f"https://api.macvendors.com/{oui}"
        req = urllib.request.Request(url, headers={"User-Agent": "routeros-toolkit/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            vendor = resp.read().decode("utf-8").strip()
            cache[oui] = vendor
            time.sleep(1.1)   # respetar el rate limit
            return vendor
    except Exception:
        cache[oui] = ""
        return ""


def resolve_device_name(ip: str, mac: str, hostname: str,
                        is_static: bool = False) -> str:
    """
    Construye el nombre más descriptivo posible para un dispositivo.

    Prioridad:
      1. Hostname DHCP (si existe y no es genérico como 'wlan0')
      2. Vendor del MAC + últimos 4 dígitos MAC (ej: "Amazon :3D:58")
      3. MAC completa como fallback

    Args:
        ip        — IP del dispositivo
        mac       — Dirección MAC (AA:BB:CC:DD:EE:FF)
        hostname  — Nombre de host reportado por DHCP
        is_static — True si la IP fue asignada estáticamente

    Returns:
        String con el nombre más descriptivo disponible.
    """
    vendor_cache = get_mac_vendor_cache()
    oui    = mac[:8].upper() if mac else ""
    vendor = vendor_cache.get(oui, "")
    random = is_random_mac(mac) if mac else False

    # Si la MAC es aleatoria y no hay hostname, marcarla claramente
    if random and not vendor:
        vendor = "📱 MAC privada"

    # Nombres genéricos de interfaces de red — no son útiles
    generic_names = {"wlan0", "wlan1", "eth0", "eth1", "lwip", "android"}
    clean_hostname = hostname.strip() if hostname else ""

    if clean_hostname and clean_hostname.lower() not in generic_names:
        label = clean_hostname
    elif vendor and mac:
        short_mac = mac[-5:].upper()
        label = f"{vendor} :{short_mac}"
    elif mac:
        label = mac
    else:
        label = ip

    if is_static:
        label += " [estática]"

    return label


# ---------------------------------------------------------------------------
# Detección de la red LAN
# ---------------------------------------------------------------------------

def get_lan_prefix(api) -> str:
    """
    Detecta el prefijo de la subred LAN (ej: "192.168.5.").

    Prioridad:
        1. Variable de entorno MIKROTIK_LAN_PREFIX (override manual)
        2. Dirección del router en /ip/address cuya interfaz sea un bridge
        3. Primera dirección privada encontrada en /ip/address
        4. LAN_PREFIX como último recurso ("192.168.")

    El prefijo retornado siempre termina en "." y sirve para
    str.startswith() sobre IPs de la LAN.
    """
    override = os.environ.get("MIKROTIK_LAN_PREFIX", "").strip()
    if override:
        return override if override.endswith(".") else override + "."

    try:
        addresses = api.command("/ip/address/print")
    except Exception:
        return LAN_PREFIX

    private = ("192.168.", "10.", "172.16.", "172.17.", "172.18.",
               "172.19.", "172.2", "172.30.", "172.31.")

    candidates = []
    for addr in addresses:
        ip = addr.get("address", "").split("/")[0]
        if not ip or not ip.startswith(private):
            continue
        prefix = ip.rsplit(".", 1)[0] + "."
        if "bridge" in addr.get("interface", "").lower():
            return prefix          # la LAN cuelga del bridge
        candidates.append(prefix)

    return candidates[0] if candidates else LAN_PREFIX


# ---------------------------------------------------------------------------
# Mapa de dispositivos de la red (DHCP + ARP)
# ---------------------------------------------------------------------------

def build_device_map(api, by: str = "ip") -> dict:
    """
    Construye el inventario de dispositivos combinando DHCP leases y ARP.
    Las IPs que aparecen en ARP pero no en DHCP se marcan como estáticas.

    Args:
        api — instancia conectada de MikroTikAPI
        by  — clave del dict resultante: "ip" (default) o "mac"
              (MAC en mayúsculas; descarta entradas sin MAC)

    Returns:
        dict clave → {"ip", "mac", "hostname", "name", "static"}
    """
    devices: dict = {}
    lan = get_lan_prefix(api)

    for l in api.command("/ip/dhcp-server/lease/print"):
        ip = l.get("address", "")
        mac = l.get("mac-address", "")
        hostname = l.get("host-name", "")
        devices[ip] = {
            "ip": ip, "mac": mac, "hostname": hostname,
            "name": resolve_device_name(ip, mac, hostname, False),
            "static": False,
        }

    for e in api.command("/ip/arp/print"):
        ip = e.get("address", "")
        mac = e.get("mac-address", "")
        if ip.startswith(lan) and ip not in devices:
            devices[ip] = {
                "ip": ip, "mac": mac, "hostname": "",
                "name": resolve_device_name(ip, mac, "", True),
                "static": True,
            }

    if by == "mac":
        return {d["mac"].upper(): d for d in devices.values() if d["mac"]}
    return devices


def build_name_map(api) -> dict:
    """Mapa simple IP → nombre descriptivo (ver build_device_map)."""
    return {ip: d["name"] for ip, d in build_device_map(api).items()}


# ---------------------------------------------------------------------------
# Reloj del router (/system/clock)
# ---------------------------------------------------------------------------

_MESES_ROS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def parse_router_date(d: str) -> Optional[date]:
    """Convierte la fecha del router a date: 'jul/02/2026' (v6) o '2026-07-02' (v7)."""
    d = d.strip().lower()
    try:
        if "/" in d:
            mes, dia, anio = d.split("/")
            return date(int(anio), _MESES_ROS[mes], int(dia))
        if "-" in d:
            anio, mes, dia = d.split("-")
            return date(int(anio), int(mes), int(dia))
    except (ValueError, KeyError):
        pass
    return None


def get_router_datetime(api) -> Optional[datetime]:
    """Fecha y hora actuales según el reloj del router, o None si no se
    pueden interpretar (el llamador puede caer al reloj local)."""
    try:
        clock = api.command("/system/clock/print")[0]
    except (IndexError, RuntimeError):
        return None
    fecha = parse_router_date(clock.get("date", ""))
    partes = clock.get("time", "").split(":")
    if fecha is None or len(partes) < 2:
        return None
    try:
        h, m = int(partes[0]), int(partes[1])
        s = int(partes[2]) if len(partes) > 2 else 0
    except ValueError:
        return None
    return datetime(fecha.year, fecha.month, fecha.day, h, m, s)


# ---------------------------------------------------------------------------
# Caché OUI → fabricante (lib/oui_cache.json)
# ---------------------------------------------------------------------------

OUI_CACHE_FILE = Path(__file__).parent / "oui_cache.json"


def load_oui_cache() -> dict:
    """Lee el caché persistido de lookups a macvendors.com."""
    if OUI_CACHE_FILE.exists():
        try:
            with open(OUI_CACHE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_oui_cache(cache: dict):
    """Persiste el caché de fabricantes (mejor esfuerzo, sin lanzar)."""
    try:
        with open(OUI_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Salida en terminal
# ---------------------------------------------------------------------------

def print_header(title: str, width: int = 70):
    """Encabezado estándar de sección usado por los scripts."""
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


# ---------------------------------------------------------------------------
# Ejecución estándar de scripts (manejo de errores uniforme)
# ---------------------------------------------------------------------------

def run_script(main_fn):
    """
    Ejecuta el main() de un script con manejo de errores estándar:
    mensajes limpios en español (nunca tracebacks) y exit codes fijos.

    Exit codes:
        0   — OK
        1   — error de conexión o de login
        2   — error de RouterOS (!trap) o de configuración
        130 — cancelado con Ctrl+C

    Uso (al final de cada script):
        if __name__ == "__main__":
            run_script(main)
    """
    import sys
    from .app_config import ConfigError

    def _fail(code: int, msg: str, *hints: str):
        print(f"\n  {C.ERR}❌ {msg}{C.RESET}")
        for hint in hints:
            print(f"  {C.DIM}💡 {hint}{C.RESET}")
        print()
        sys.exit(code)

    try:
        main_fn()
    except KeyboardInterrupt:
        print(f"\n\n  {C.DIM}Cancelado.{C.RESET}\n")
        sys.exit(130)
    except MikroTikConnectionError as e:
        _fail(1, f"No se pudo iniciar sesión: {e}",
              "Verifica MIKROTIK_USER y MIKROTIK_PASSWORD en config.env")
    except ConnectionRefusedError:
        _fail(1, "El router rechazó la conexión (connection refused).",
              "¿Está habilitada la API?  En el router: /ip service enable api",
              "Verifica MIKROTIK_HOST y MIKROTIK_PORT en config.env")
    except socket.timeout:
        _fail(1, "Tiempo de espera agotado conectando al router.",
              "¿El host de config.env es correcto y el router está encendido?",
              "Puedes subir el límite con MIKROTIK_TIMEOUT (segundos)")
    except ConnectionError as e:
        _fail(1, f"La conexión con el router se interrumpió: {e}")
    except OSError as e:
        _fail(1, f"Error de red: {e}",
              "¿El host de config.env es correcto y hay ruta hacia el router?")
    except MikroTikCommandError as e:
        _fail(2, str(e),
              "El router rechazó la operación; revisa permisos del usuario "
              "y los datos enviados")
    except ConfigError as e:
        _fail(2, str(e))


# ---------------------------------------------------------------------------
# Colores ANSI para terminal
# ---------------------------------------------------------------------------

class C:
    """
    Códigos de escape ANSI para colorear salida de terminal.

    Uso:
        print(f"{C.RED}error{C.RESET}")
        print(f"{C.BOLD}{C.CYAN}título{C.RESET}")

    Para deshabilitar colores (ej: redirección a archivo):
        C.disable()
    """
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"

    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"

    # Combos útiles
    HEADER = "\033[1;96m"   # bold cyan
    OK     = "\033[92m"     # green
    WARN   = "\033[93m"     # yellow
    ERR    = "\033[91m"     # red

    @classmethod
    def disable(cls):
        """Elimina todos los códigos de color (útil al redirigir a archivo)."""
        for attr in ["RESET","BOLD","DIM","RED","GREEN","YELLOW",
                     "BLUE","CYAN","WHITE","GRAY","HEADER","OK","WARN","ERR"]:
            setattr(cls, attr, "")

    @classmethod
    def speed_color(cls, bps: int) -> str:
        """Retorna color según la velocidad: verde < 1 Mbps, amarillo < 10, rojo ≥ 10."""
        if bps >= 10_000_000:
            return cls.RED
        elif bps >= 1_000_000:
            return cls.YELLOW
        elif bps > 0:
            return cls.GREEN
        return cls.GRAY
