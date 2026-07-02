"""
test_core.py — Tests directos de la capa core/ (Fase 0 del frontend)
=====================================================================

Cubre la lógica extraída de los scripts que no estaba pineada por otros
tests: consumo (monitoreo), clasificación de dispositivos, bloqueos,
reglas de horario y filtros/diagnóstico QoS. Usa una API falsa;
no requiere router.
"""

import unittest

from core.bloqueos import (COMMENT_TAG, reglas_bloqueo, buscar_bloqueo,
                           bloquear_ip, desbloquear_ip)
from core.dispositivos import (guess_device_type, fmt_lease_time,
                               filtrar_dispositivos)
from core.horario import apply_all_rules, remove_all_rules, DROP_TAG, ALLOW_TAG
from core.monitoreo import (snapshot_consumo, ordenar_consumo,
                            calcular_delta, interfaz_mas_activa,
                            resumen_sistema, nivel_log)
from core.qos import (filtrar_mangle_qos, filtrar_colas_qos,
                      agrupar_por_prioridad, rehabilitar_fasttrack)


class FakeAPI:
    """Simula MikroTikAPI.command() con respuestas predefinidas."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.writes = []

    def command(self, cmd, params=None, queries=None):
        if params:
            self.writes.append((cmd, params))
        return self.responses.get(cmd, [])


# ---------------------------------------------------------------------------
# core.monitoreo
# ---------------------------------------------------------------------------

class TestSnapshotConsumo(unittest.TestCase):

    def _api(self):
        return FakeAPI({"/ip/firewall/connection/print": [
            # Kevin: rates + bytes normales + fasttrack
            {"src-address": "192.168.5.22:5000", "repl-rate": "1000",
             "orig-rate": "100", "repl-bytes": "500",
             "repl-fasttrack-bytes": "500", "orig-bytes": "50",
             "orig-fasttrack-bytes": "50"},
            {"src-address": "192.168.5.22:6000", "repl-rate": "2000",
             "orig-rate": "200", "repl-bytes": "1000", "orig-bytes": "100"},
            # Otro dispositivo
            {"src-address": "192.168.5.30:1234", "repl-rate": "50",
             "orig-rate": "5", "repl-bytes": "10", "orig-bytes": "1"},
            # Fuera de la LAN: se ignora
            {"src-address": "8.8.8.8:53", "repl-rate": "9999",
             "repl-bytes": "9999"},
        ]})

    def test_acumula_por_ip_y_suma_fasttrack(self):
        data, total = snapshot_consumo(self._api(), "192.168.")
        self.assertEqual(total, 4)          # conexiones totales (incluye WAN)
        self.assertEqual(set(data), {"192.168.5.22", "192.168.5.30"})
        kevin = data["192.168.5.22"]
        self.assertEqual(kevin["dl_rate"], 3000)
        self.assertEqual(kevin["ul_rate"], 300)
        # 500 + 500 (fasttrack) + 1000 = 2000
        self.assertEqual(kevin["dl_total"], 2000)
        self.assertEqual(kevin["ul_total"], 200)
        self.assertEqual(kevin["conns"], 2)

    def test_ordenar_por_rate_y_total(self):
        data, _ = snapshot_consumo(self._api(), "192.168.")
        por_rate = ordenar_consumo(data, por="rate")
        self.assertEqual(por_rate[0][0], "192.168.5.22")
        por_total = ordenar_consumo(data, por="total")
        self.assertEqual(por_total[0][0], "192.168.5.22")
        self.assertEqual(por_total[1][0], "192.168.5.30")


class TestInterfaces(unittest.TestCase):

    def test_calcular_delta_e_interfaz_mas_activa(self):
        s1 = {"ether1": {"tx-byte": "100", "rx-byte": "200"},
              "bridge1": {"tx-byte": "10", "rx-byte": "10"}}
        s2 = {"ether1": {"tx-byte": "600", "rx-byte": "300"},
              "bridge1": {"tx-byte": "20", "rx-byte": "15"},
              "ether9": {"tx-byte": "5", "rx-byte": "5"}}   # nueva: sin delta
        delta = calcular_delta(s1, s2)
        self.assertEqual(delta["ether1"], {"tx-byte": 500, "rx-byte": 100})
        self.assertEqual(delta["bridge1"], {"tx-byte": 10, "rx-byte": 5})
        self.assertNotIn("ether9", delta)
        self.assertEqual(interfaz_mas_activa(delta)[0], "ether1")
        self.assertIsNone(interfaz_mas_activa({}))

    def test_delta_nunca_negativo(self):
        # Contadores reiniciados (reboot del router)
        s1 = {"ether1": {"tx-byte": "9999", "rx-byte": "9999"}}
        s2 = {"ether1": {"tx-byte": "5", "rx-byte": "5"}}
        delta = calcular_delta(s1, s2)
        self.assertEqual(delta["ether1"], {"tx-byte": 0, "rx-byte": 0})


class TestResumenSistema(unittest.TestCase):

    def test_estructura_y_casteos(self):
        api = FakeAPI({
            "/system/resource/print": [{
                "uptime": "1w2d", "version": "6.49.19", "board-name": "hEX lite",
                "architecture-name": "smips", "cpu-count": "1", "cpu-load": "7",
                "free-memory": "40000000", "total-memory": "64000000",
                "free-hdd-space": "10000000", "total-hdd-space": "16000000",
            }],
            "/system/identity/print": [{"name": "DUOTICS"}],
            "/interface/print": [{"running": "true"}, {"running": "false"}],
            "/ip/dhcp-server/lease/print": [{"status": "bound"},
                                            {"status": "waiting"}],
        })
        info = resumen_sistema(api)
        self.assertEqual(info["name"], "DUOTICS")
        self.assertEqual(info["cpu_load"], 7)
        self.assertEqual(info["used_mem"], 24000000)
        self.assertEqual(info["used_hdd"], 6000000)
        self.assertEqual(info["ifaces_up"], 1)
        self.assertEqual(info["ifaces_total"], 2)
        self.assertEqual(info["devices_conn"], 1)

    def test_sin_resource_retorna_none(self):
        self.assertIsNone(resumen_sistema(FakeAPI({})))


class TestNivelLog(unittest.TestCase):

    def test_niveles(self):
        self.assertEqual(nivel_log("system,error"), "error")
        self.assertEqual(nivel_log("system,critical"), "critical")
        self.assertEqual(nivel_log("wireless,warning"), "warning")
        self.assertEqual(nivel_log("dhcp,info"), "info")
        self.assertEqual(nivel_log(""), "info")


# ---------------------------------------------------------------------------
# core.dispositivos
# ---------------------------------------------------------------------------

class TestGuessDeviceType(unittest.TestCase):

    def test_apple_por_oui(self):
        self.assertEqual(guess_device_type("F0:18:98:11:22:33", "", ""),
                         "🍎 Apple")

    def test_apple_por_hostname(self):
        self.assertEqual(guess_device_type("AA:BB:CC:11:22:33", "iPhone-de-Ana", ""),
                         "🍎 Apple")

    def test_mac_privada(self):
        # Segundo dígito 2/6/A/E = MAC aleatoria
        tipo = guess_device_type("A2:BB:CC:11:22:33", "", "")
        self.assertIn("MAC privada", tipo)

    def test_movil_por_hostname(self):
        self.assertEqual(guess_device_type("00:11:22:33:44:55", "redmi-note", ""),
                         "📱 Móvil")

    def test_desconocido(self):
        self.assertEqual(guess_device_type("00:11:22:33:44:55", "", ""),
                         "❓ Desconocido")


class TestFmtLeaseTime(unittest.TestCase):

    def test_fija(self):
        self.assertEqual(fmt_lease_time("never"), "∞ fija")
        self.assertEqual(fmt_lease_time(""), "∞ fija")

    def test_duracion(self):
        self.assertEqual(fmt_lease_time("2d3:00:00"), "2d 3h")
        self.assertEqual(fmt_lease_time("0d5:30:00"), "5h 30m")
        self.assertEqual(fmt_lease_time("0d0:12:00"), "12m")


class TestFiltrarDispositivos(unittest.TestCase):

    RESULTS = [
        {"type": "🍎 Apple", "vendor": "Apple"},
        {"type": "📱 Móvil", "vendor": "Xiaomi"},
        {"type": "❓ Desconocido", "vendor": ""},
        {"type": "🏠 IoT/Smart", "vendor": "Espressif"},
    ]

    def test_filtros(self):
        self.assertEqual(len(filtrar_dispositivos(self.RESULTS, "apple")), 1)
        self.assertEqual(len(filtrar_dispositivos(self.RESULTS, "mobile")), 1)
        self.assertEqual(len(filtrar_dispositivos(self.RESULTS, "iot")), 1)
        self.assertEqual(len(filtrar_dispositivos(self.RESULTS, "unknown")), 1)
        self.assertEqual(filtrar_dispositivos(self.RESULTS, ""), self.RESULTS)
        self.assertEqual(filtrar_dispositivos(self.RESULTS, None), self.RESULTS)


# ---------------------------------------------------------------------------
# core.bloqueos
# ---------------------------------------------------------------------------

class TestBloqueos(unittest.TestCase):

    def _api(self):
        return FakeAPI({"/ip/firewall/filter/print": [
            {".id": "*1", "src-address": "192.168.5.30",
             "comment": f"{COMMENT_TAG}-192.168.5.30"},
            {".id": "*2", "comment": "HORARIO-INTERNET"},   # ajena: no se toca
            {".id": "*3", "src-address": "192.168.5.40",
             "comment": f"{COMMENT_TAG}-192.168.5.40"},
        ]})

    def test_reglas_bloqueo_solo_propias(self):
        reglas = reglas_bloqueo(self._api())
        self.assertEqual([r[".id"] for r in reglas], ["*1", "*3"])

    def test_buscar_bloqueo(self):
        self.assertEqual(len(buscar_bloqueo(self._api(), "192.168.5.30")), 1)
        self.assertEqual(buscar_bloqueo(self._api(), "192.168.5.99"), [])

    def test_bloquear_ip_crea_regla_etiquetada(self):
        api = FakeAPI({})
        bloquear_ip(api, "192.168.5.50")
        self.assertEqual(len(api.writes), 1)
        cmd, params = api.writes[0]
        self.assertEqual(cmd, "/ip/firewall/filter/add")
        self.assertIn("=action=drop", params)
        self.assertIn("=src-address=192.168.5.50", params)
        self.assertIn(f"=comment={COMMENT_TAG}-192.168.5.50", params)
        self.assertIn("=place-before=0", params)

    def test_desbloquear_ip_elimina_solo_la_suya(self):
        api = self._api()
        n = desbloquear_ip(api, "192.168.5.30")
        self.assertEqual(n, 1)
        self.assertEqual(api.writes,
                         [("/ip/firewall/filter/remove", ["=.id=*1"])])

    def test_desbloquear_inexistente(self):
        api = self._api()
        self.assertEqual(desbloquear_ip(api, "192.168.5.99"), 0)
        self.assertEqual(api.writes, [])


# ---------------------------------------------------------------------------
# core.horario (reglas en el router; las funciones puras ya tienen tests)
# ---------------------------------------------------------------------------

class TestHorarioReglas(unittest.TestCase):

    def test_apply_all_rules_orden_accept_luego_drop(self):
        api = FakeAPI({})
        apply_all_rules(api, "ether1", "01:00:00", "06:00:00",
                        ["mon", "tue"], ["AA:BB:CC:11:22:33"])
        self.assertEqual(len(api.writes), 2)
        # Primero la ACCEPT de la lista blanca…
        cmd0, params0 = api.writes[0]
        self.assertIn("=action=accept", params0)
        self.assertIn(f"=comment={ALLOW_TAG}-AA:BB:CC:11:22:33", params0)
        # …después la DROP global con horario
        cmd1, params1 = api.writes[1]
        self.assertIn("=action=drop", params1)
        self.assertIn("=time=01:00:00-06:00:00,mon,tue", params1)
        self.assertIn(f"=comment={DROP_TAG}", params1)

    def test_remove_all_rules_solo_propias(self):
        api = FakeAPI({"/ip/firewall/filter/print": [
            {".id": "*1", "comment": DROP_TAG},
            {".id": "*2", "comment": f"{ALLOW_TAG}-AA:BB:CC:11:22:33"},
            {".id": "*3", "comment": "BLOQUEADO-POR-MENU-192.168.5.30"},
            {".id": "*4", "comment": ""},
        ]})
        n = remove_all_rules(api)
        self.assertEqual(n, 2)
        removidas = [p[0] for _, p in api.writes]
        self.assertEqual(removidas, ["=.id=*1", "=.id=*2"])


# ---------------------------------------------------------------------------
# core.qos (filtros del reset selectivo + diagnóstico)
# ---------------------------------------------------------------------------

class TestQosFiltros(unittest.TestCase):

    def test_filtrar_mangle_qos(self):
        mangle = [
            {"comment": "QoS P1 - DNS UDP"},
            {"comment": "regla manual"},
            {"comment": "QoS P8 - bulk"},
            {},
        ]
        self.assertEqual(len(filtrar_mangle_qos(mangle)), 2)

    def test_filtrar_colas_qos(self):
        colas = [
            {"name": "QoS_Download"},
            {"name": "DL-2-Kevin"},
            {"name": "UL-8-Bulk"},
            {"name": "cola-manual"},
        ]
        self.assertEqual(len(filtrar_colas_qos(colas)), 3)

    def test_agrupar_por_prioridad(self):
        mangle = [
            {"comment": "QoS P2 - Kevin origen", "bytes": "100", "packets": "1"},
            {"comment": "QoS P2 - Kevin destino", "bytes": "200", "packets": "2"},
            {"comment": "QoS P8 - bulk", "bytes": "50", "packets": "5"},
            {"comment": "sin prioridad", "bytes": "1", "packets": "1"},
        ]
        marks = agrupar_por_prioridad(mangle)
        self.assertEqual(marks["P2_Kevin"]["bytes"], 300)
        self.assertEqual(marks["P2_Kevin"]["packets"], 3)
        self.assertEqual(len(marks["P2_Kevin"]["rules"]), 2)
        self.assertEqual(marks["P8_Bulk"]["bytes"], 50)
        self.assertIn("unknown", marks)

    def test_rehabilitar_fasttrack_selectivo(self):
        api = FakeAPI({"/ip/firewall/filter/print": []})
        api.responses["/ip/firewall/filter/print"] = [
            {".id": "*1", "disabled": "true"},
            {".id": "*2", "disabled": "false"},
        ]
        # Ojo: buscar_fasttrack usa queries, la FakeAPI responde igual
        habilitadas, total = rehabilitar_fasttrack(api, solo_deshabilitadas=True)
        self.assertEqual((habilitadas, total), (1, 2))
        self.assertEqual(api.writes,
                         [("/ip/firewall/filter/set", ["=.id=*1", "=disabled=no"])])

    def test_rehabilitar_fasttrack_forzado(self):
        api = FakeAPI({"/ip/firewall/filter/print": [
            {".id": "*1", "disabled": "true"},
            {".id": "*2", "disabled": "false"},
        ]})
        habilitadas, total = rehabilitar_fasttrack(api, solo_deshabilitadas=False)
        self.assertEqual((habilitadas, total), (2, 2))


if __name__ == "__main__":
    unittest.main()
