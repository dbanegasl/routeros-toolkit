/**
 * types.ts — Formas de las respuestas de la API (espejo del backend).
 */

export interface Sistema {
  name: string;
  uptime: string;
  version: string;
  board: string;
  cpu_load: number;
  used_mem: number;
  total_mem: number;
  used_hdd: number;
  total_hdd: number;
  ifaces_up: number;
  ifaces_total: number;
  devices_conn: number;
}

export interface Dispositivo {
  ip: string;
  mac: string;
  nombre: string;
  estado: string;
  puerto: string;
  tipo: "DHCP" | "STATIC";
}

export interface DispositivosResp {
  total: number;
  dispositivos: Dispositivo[];
}

export interface WhitelistItem {
  mac: string;
  nombre: string;
  ip: string | null;
  en_red: boolean;
  aplicada_en_router: boolean;
  bytes: number;
}

export interface Horario {
  corte: {
    inicio: string;
    fin: string;
    dias: string[];
    dias_etiquetas: string[];
    interfaz_wan: string;
    paquetes_bloqueados: number;
    bytes_bloqueados: number;
  } | null;
  en_curso: boolean;
  hora_actual?: string;
  whitelist: WhitelistItem[];
}

export interface Validacion {
  identidad: { nombre: string; version: string; equipo: string };
  qos: { mangle: number; queue_tree: number; queue_simple: number; activo: boolean };
  reloj: {
    deriva_segundos: number | null;
    sincronizado: boolean;
    ntp_habilitado: boolean | null;
  };
}

export interface ConsumoDispositivo {
  ip: string;
  nombre: string;
  dl_rate: number;
  ul_rate: number;
  dl_total: number;
  ul_total: number;
  conexiones: number;
}

export interface Consumo {
  conexiones_totales: number;
  dispositivos: ConsumoDispositivo[];
}

export interface Sesion {
  autenticada: boolean;
}

// ── Mensajes de WebSocket ────────────────────────────────────────────

export interface InterfazViva {
  nombre: string;
  activa: boolean;
  tx_rate: number;
  rx_rate: number;
  tx_total: number;
  rx_total: number;
}

export interface MonitorMsg {
  ts: number;
  error?: string;
  conexiones_totales: number;
  dispositivos: ConsumoDispositivo[];
  interfaces: InterfazViva[];
}

export interface LogEntrada {
  hora: string;
  topics: string;
  mensaje: string;
  nivel: "critical" | "error" | "warning" | "info" | "debug";
}

export interface LogMsg {
  ts: number;
  error?: string;
  entradas: LogEntrada[];
}
