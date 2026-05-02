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
import os
from pathlib import Path
from typing import Optional


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

    return {
        "host":     config.get("MIKROTIK_HOST", "192.168.5.1"),
        "port":     int(config.get("MIKROTIK_PORT", 8728)),
        "username": config.get("MIKROTIK_USER", "admin"),
        "password": config.get("MIKROTIK_PASSWORD", ""),
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

        if resp and resp[0] == "!done":
            return  # Login exitoso

        # Intento 2: challenge MD5 (RouterOS < 6.43)
        challenge = None
        for word in resp:
            if word.startswith("=ret="):
                challenge = bytes.fromhex(word[5:])
                break

        if challenge is None:
            raise RuntimeError(f"Login fallido: {resp}")

        md5 = hashlib.md5()
        md5.update(b"\x00")
        md5.update(self.password.encode("utf-8"))
        md5.update(challenge)
        self._send_sentence(["/login",
                             f"=name={self.username}",
                             f"=response=00{md5.hexdigest()}"])
        resp2 = self._recv_sentence()
        if not resp2 or resp2[0] != "!done":
            raise RuntimeError(f"Login MD5 fallido: {resp2}")

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
                raise RuntimeError(f"RouterOS error: {error}")
            elif tag == "!fatal":
                raise RuntimeError(f"RouterOS fatal: {words}")

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


def get_mac_vendor_cache() -> dict:
    """
    Retorna un dict con prefijos OUI conocidos (sin necesitar internet).
    Clave: primeros 8 caracteres de la MAC en mayúsculas (AA:BB:CC).
    Se puede extender manualmente con más entradas.
    """
    return {
        # Computadoras / placas madre
        "F0:2F:74": "ASUSTeK",
        "D8:5E:D3": "GIGABYTE",
        "00:1E:C2": "Apple",
        "00:90:A9": "Intel/Xircom",
        "FC:3C:D7": "Foxconn",
        "84:28:59": "Liteon/Realtek",
        "10:BF:67": "Intel",
        "9C:53:22": "Intel",
        # Amazon (Echo, Fire, plugs, Ring, Blink)
        "8C:2A:85": "Amazon",
        "08:7C:39": "Amazon",
        "74:58:F3": "Amazon",
        "08:57:FB": "Amazon",
        "74:AB:93": "Blink (Amazon)",
        "00:F3:61": "Amazon",
        # TP-Link
        "DC:62:79": "TP-Link",
        "54:D6:0D": "TP-Link",
        "A8:80:55": "TP-Link",
        # Hikvision / EZVIZ
        "60:DC:81": "EZVIZ/Hikvision",
        # Google / Nest
        "44:07:0B": "Google",
        # Impresoras
        "B0:E8:92": "Epson",
        # Xiaomi / Redmi / POCO
        "F6:4F:F8": "Xiaomi (random)",
        "22:AE:16": "Xiaomi (random)",
        "3A:F9:EE": "Xiaomi (random)",
        # Samsung
        "A6:E5:35": "Samsung (random)",
        "64:1C:AE": "Samsung",
        # Otros
        "38:1F:8D": "Realtek",
        "18:DE:50": "Broadcom",
        "DC:29:19": "Espressif (IoT)",
        "92:03:D7": "Desconocido",
        "7C:C2:C6": "Desconocido",
        "7C:63:05": "Desconocido",
        "C0:91:B9": "Desconocido",
        "52:2C:81": "Desconocido (random)",
        "3A:3C:EB": "Desconocido (random)",
    }


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
    vendor = vendor_cache.get(mac[:8].upper(), "") if mac else ""

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
