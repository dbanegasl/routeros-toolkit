"""
test_qos_builders.py — Tests de las funciones puras del despliegue QoS
=======================================================================

build_mangle_rules / build_queue_tree de scripts/10_deploy_qos.py.
Verifica que los defaults generen EXACTAMENTE el plan original y que
la configuración externa (IP, interfaces, escalado) se aplique bien.
No requiere router.
"""

import importlib.util
import os
import sys
import unittest
from pathlib import Path

# Importar el script 10 como módulo (su nombre empieza con dígito)
_spec = importlib.util.spec_from_file_location(
    "deploy_qos",
    Path(__file__).resolve().parent.parent / "scripts" / "10_deploy_qos.py")
deploy_qos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deploy_qos)

QOS_DEFAULTS = deploy_qos.QOS_DEFAULTS


def custom_qos(**overrides) -> dict:
    qos = {k: (dict(v) if isinstance(v, dict) else v)
           for k, v in QOS_DEFAULTS.items()}
    for key, value in overrides.items():
        if isinstance(value, dict):
            qos[key].update(value)
        else:
            qos[key] = value
    return qos


class TestBuildMangleRules(unittest.TestCase):

    def test_defaults_generan_plan_original(self):
        rules = deploy_qos.build_mangle_rules(QOS_DEFAULTS)
        self.assertEqual(len(rules), 23)
        # IP de Kevin en las reglas de origen/destino
        srcs = [r for r in rules if r.get("src-address")]
        dsts = [r for r in rules if r.get("dst-address")]
        self.assertEqual(srcs[0]["src-address"], "192.168.5.22")
        self.assertEqual(dsts[0]["dst-address"], "192.168.5.22")
        # Umbral bulk original
        bulk = [r for r in rules if "connection-bytes" in r][0]
        self.assertEqual(bulk["connection-bytes"], "30000000-0")
        self.assertIn(">30MB", bulk["comment"])
        # Alias en comentarios (primer nombre)
        self.assertIn("Kevin origen", srcs[0]["comment"])

    def test_ip_configurable(self):
        qos = custom_qos(dispositivo_prioritario={
            "nombre": "María López", "ip": "192.168.5.99"})
        rules = deploy_qos.build_mangle_rules(qos)
        srcs = [r for r in rules if r.get("src-address")]
        self.assertEqual(srcs[0]["src-address"], "192.168.5.99")
        self.assertIn("María origen", srcs[0]["comment"])

    def test_umbral_bulk_configurable(self):
        rules = deploy_qos.build_mangle_rules(custom_qos(umbral_bulk_mb=50))
        bulk = [r for r in rules if "connection-bytes" in r][0]
        self.assertEqual(bulk["connection-bytes"], "50000000-0")
        self.assertIn(">50MB", bulk["comment"])

    def test_todas_las_marcas_de_paquete_presentes(self):
        rules = deploy_qos.build_mangle_rules(QOS_DEFAULTS)
        marks = {r["new-packet-mark"] for r in rules
                 if "new-packet-mark" in r}
        self.assertEqual(marks, {"pkt_critico", "pkt_kevin", "pkt_bulk",
                                 "pkt_trabajo", "pkt_streaming",
                                 "pkt_web", "pkt_resto"})


class TestBuildQueueTree(unittest.TestCase):

    def test_defaults_generan_plan_original(self):
        queues = deploy_qos.build_queue_tree(QOS_DEFAULTS)
        self.assertEqual(len(queues), 16)
        by_name = {q["name"]: q for q in queues}
        self.assertEqual(by_name["QoS_Download"]["parent"], "bridge1")
        self.assertEqual(by_name["QoS_Upload"]["parent"], "ether1")
        self.assertEqual(by_name["QoS_Download"]["max-limit"], "85M")
        self.assertEqual(by_name["DL-2-Kevin"]["limit-at"], "30M")
        self.assertEqual(by_name["UL-8-Bulk"]["limit-at"], "512k")

    def test_interfaces_configurables(self):
        qos = custom_qos(bridge_lan="bridge-casa", interfaz_wan="ether5")
        by_name = {q["name"]: q for q in deploy_qos.build_queue_tree(qos)}
        self.assertEqual(by_name["QoS_Download"]["parent"], "bridge-casa")
        self.assertEqual(by_name["QoS_Upload"]["parent"], "ether5")

    def test_escalado_50_mbps_solo_download(self):
        qos = custom_qos(descarga_total_mbps=50)
        by_name = {q["name"]: q for q in deploy_qos.build_queue_tree(qos)}
        self.assertEqual(by_name["QoS_Download"]["max-limit"], "42M")
        self.assertEqual(by_name["DL-2-Kevin"]["limit-at"], "15M")
        # Upload no cambia
        self.assertEqual(by_name["QoS_Upload"]["max-limit"], "85M")
        self.assertEqual(by_name["UL-2-Kevin"]["limit-at"], "30M")

    def test_escalado_nunca_baja_de_1(self):
        """Con anchos muy bajos, ningún límite queda en 0 (RouterOS lo rechaza)."""
        qos = custom_qos(descarga_total_mbps=1, subida_total_mbps=1)
        for q in deploy_qos.build_queue_tree(qos):
            for key in ("limit-at", "max-limit"):
                if key in q:
                    self.assertGreaterEqual(int(q[key][:-1]), 1,
                                            f"{q['name']}.{key} = {q[key]}")

    def test_nombre_en_comentarios(self):
        qos = custom_qos(dispositivo_prioritario={"nombre": "María López"})
        by_name = {q["name"]: q for q in deploy_qos.build_queue_tree(qos)}
        self.assertIn("María López", by_name["DL-2-Kevin"]["comment"])
        self.assertIn("María OBS", by_name["UL-2-Kevin"]["comment"])


class TestScaleLimit(unittest.TestCase):

    def test_factor_uno_intacto(self):
        self.assertEqual(deploy_qos._scale_limit("85M", 1.0), "85M")
        self.assertEqual(deploy_qos._scale_limit("512k", 1.0), "512k")

    def test_escala_proporcional(self):
        self.assertEqual(deploy_qos._scale_limit("30M", 0.5), "15M")
        self.assertEqual(deploy_qos._scale_limit("512k", 0.5), "256k")
        self.assertEqual(deploy_qos._scale_limit("85M", 2.0), "170M")


class TestLoadQosConfig(unittest.TestCase):

    def test_sin_archivo_usa_defaults(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"MIKROTIK_CONFIG_DIR": tmp}):
            qos = deploy_qos.load_qos_config()
        self.assertEqual(qos["dispositivo_prioritario"]["mac"],
                         "F0:2F:74:CB:97:3F")
        self.assertEqual(qos["descarga_total_mbps"], 100)

    def test_device_parcial_se_completa(self):
        import tempfile
        from unittest import mock
        from lib.app_config import save_json_config
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.dict(os.environ, {"MIKROTIK_CONFIG_DIR": tmp}):
            save_json_config("qos", {
                "dispositivo_prioritario": {"ip": "192.168.5.77"}})
            qos = deploy_qos.load_qos_config()
        self.assertEqual(qos["dispositivo_prioritario"]["ip"], "192.168.5.77")
        # nombre/mac completados desde defaults
        self.assertEqual(qos["dispositivo_prioritario"]["nombre"],
                         "Kevin KUTOGG")


if __name__ == "__main__":
    unittest.main()
