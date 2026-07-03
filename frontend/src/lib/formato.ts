/**
 * formato.ts — Formateo de bytes y velocidades.
 *
 * Mismos umbrales y unidades que fmt_bytes / fmt_speed de lib/ (Python),
 * para que el panel y el CLI muestren los mismos números.
 */

export function fmtBytes(b: number): string {
  if (b >= 1_073_741_824) return `${(b / 1_073_741_824).toFixed(2)} GB`;
  if (b >= 1_048_576) return `${(b / 1_048_576).toFixed(2)} MB`;
  if (b >= 1_024) return `${(b / 1_024).toFixed(1)} KB`;
  return `${b} B`;
}

export function fmtVelocidad(bps: number): string {
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(2)} Mbps`;
  if (bps >= 1_000) return `${(bps / 1_000).toFixed(1)} Kbps`;
  return `${bps} bps`;
}

/** Porcentaje 0–100 acotado, para barras de progreso. */
export function porcentaje(usado: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.max(0, (usado / total) * 100));
}

/** 'Uptime' de RouterOS ('2d7h10m19s') → forma corta legible ('2d 7h'). */
export function fmtUptime(uptime: string): string {
  const m = uptime.match(/(?:(\d+)w)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?/);
  if (!m) return uptime;
  const [, w, d, h, min] = m;
  const partes: string[] = [];
  if (w) partes.push(`${w}sem`);
  if (d) partes.push(`${d}d`);
  if (h) partes.push(`${h}h`);
  if (!w && !d && min) partes.push(`${min}m`);
  return partes.length ? partes.slice(0, 2).join(" ") : uptime;
}
