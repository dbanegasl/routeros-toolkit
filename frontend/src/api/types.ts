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

export interface Bloqueo {
  id: string;
  ip: string;
  comentario: string;
}

export interface BloqueosResp {
  total: number;
  bloqueos: Bloqueo[];
}

export interface WhitelistDispositivo {
  mac: string;
  nombre: string;
  ip: string | null;
  en_red: boolean;
  aplicada_en_router: boolean;
}

export interface WhitelistResp {
  dispositivos: WhitelistDispositivo[];
}

// ── QoS ──────────────────────────────────────────────────────────────

export interface QosEstado {
  activo: boolean;
  mangle_qos: number;
  mangle_ajenas: number;
  colas_qos: number;
  colas_ajenas: number;
  fasttrack_activo: boolean;
  fasttrack_reglas: number;
}

/** Reglas Mangle y colas del plan: dicts clave→valor de RouterOS. */
export type ReglaRouterOS = Record<string, string>;

export interface QosPlan {
  config: {
    dispositivo: { nombre: string; mac: string; ip: string };
    interfaz_wan: string;
    bridge_lan: string;
    descarga_total_mbps: number;
    subida_total_mbps: number;
    umbral_bulk_mb: number;
  };
  lease: { existe: boolean; ip_actual: string | null };
  estado: QosEstado;
  mangle: ReglaRouterOS[];
  colas: ReglaRouterOS[];
}

export interface QosMarca {
  prioridad: string;
  bytes: number;
  paquetes: number;
  reglas: { comentario: string; bytes: number; paquetes: number }[];
}

export interface QosColaDiag {
  nombre: string;
  padre: string;
  mark: string;
  bytes: number;
  paquetes: number;
  descartados: number;
  limite: string;
  maximo: string;
}

export interface QosDiagnostico {
  estado: QosEstado;
  marcas: QosMarca[];
  colas: QosColaDiag[];
}

// ── Respaldos ────────────────────────────────────────────────────────

export interface RespaldoLocal {
  nombre: string;
  bytes: number;
  meta: {
    creado?: string;
    hora_router?: string | null;
    routeros?: string;
    equipo?: string;
  } | null;
}

export interface RespaldoRouter {
  nombre: string;
  bytes: number;
  creado: string;
}

export interface RespaldosResp {
  locales: RespaldoLocal[];
  router: RespaldoRouter[];
}

export interface RespaldoCreado {
  mensaje: string;
  snapshot: string;
  secciones: Record<string, number>;
  backup_router: string | null;
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

export interface QosColaViva {
  nombre: string;
  mark: string;
  bytes: number;
  rate: number;
  descartados: number;
  maximo: string;
}

export interface QosMsg {
  ts: number;
  error?: string;
  activo: boolean;
  colas: QosColaViva[];
}
