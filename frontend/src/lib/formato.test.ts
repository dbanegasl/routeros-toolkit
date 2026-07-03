/**
 * formato.test.ts — Pinea que el formato coincide con lib/ (Python).
 */
import { describe, expect, it } from "vitest";

import { fmtBytes, fmtVelocidad, fmtUptime, porcentaje } from "./formato";

describe("fmtBytes (espejo de fmt_bytes)", () => {
  it("usa los mismos umbrales binarios que la lib", () => {
    expect(fmtBytes(500)).toBe("500 B");
    expect(fmtBytes(2048)).toBe("2.0 KB");
    expect(fmtBytes(1_048_576)).toBe("1.00 MB");
    expect(fmtBytes(1_073_741_824)).toBe("1.00 GB");
    expect(fmtBytes(167_246_831_733)).toBe("155.76 GB");
  });
});

describe("fmtVelocidad (espejo de fmt_speed)", () => {
  it("usa los mismos umbrales decimales que la lib", () => {
    expect(fmtVelocidad(500)).toBe("500 bps");
    expect(fmtVelocidad(1_500)).toBe("1.5 Kbps");
    expect(fmtVelocidad(2_500_000)).toBe("2.50 Mbps");
  });
});

describe("fmtUptime", () => {
  it("resume el uptime de RouterOS a dos unidades", () => {
    expect(fmtUptime("2d7h10m19s")).toBe("2d 7h");
    expect(fmtUptime("1w2d")).toBe("1sem 2d");
    expect(fmtUptime("45m10s")).toBe("45m");
    expect(fmtUptime("10s")).toBe("10s");
  });
});

describe("porcentaje", () => {
  it("acota entre 0 y 100 y tolera total 0", () => {
    expect(porcentaje(50, 100)).toBe(50);
    expect(porcentaje(200, 100)).toBe(100);
    expect(porcentaje(10, 0)).toBe(0);
  });
});
