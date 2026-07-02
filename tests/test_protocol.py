"""
test_protocol.py — Tests del protocolo binario RouterOS API
============================================================

Prueba la codificación de longitudes, sentences, login y parsing de
respuestas de lib/mikrotik_api.py usando un socket falso en memoria.
No requiere router.
"""

import hashlib
import unittest

from lib.mikrotik_api import MikroTikAPI


# ---------------------------------------------------------------------------
# Infraestructura: socket falso y codificador de referencia
# ---------------------------------------------------------------------------

class FakeSocket:
    """Socket en memoria: lo que el 'router' responde se carga en rx,
    lo que el cliente envía se acumula en tx."""

    def __init__(self, rx: bytes = b""):
        self.rx = bytearray(rx)
        self.tx = bytearray()

    def sendall(self, data: bytes):
        self.tx.extend(data)

    def recv(self, n: int) -> bytes:
        chunk = bytes(self.rx[:n])
        del self.rx[:n]
        return chunk

    def settimeout(self, t):
        pass

    def close(self):
        pass


def encode_length(length: int) -> bytes:
    """Codificador de referencia, escrito de forma independiente a la lib
    siguiendo la especificación del protocolo RouterOS."""
    if length < 0x80:
        return bytes([length])
    if length < 0x4000:
        v = length | 0x8000
        return v.to_bytes(2, "big")
    if length < 0x200000:
        v = length | 0xC00000
        return v.to_bytes(3, "big")
    v = length | 0xE0000000
    return v.to_bytes(4, "big")


def encode_sentence(words: list) -> bytes:
    """Codifica una sentence completa como la enviaría el router."""
    out = bytearray()
    for w in words:
        enc = w.encode("utf-8")
        out += encode_length(len(enc)) + enc
    out += b"\x00"
    return bytes(out)


def make_api(rx: bytes = b"") -> MikroTikAPI:
    """Crea una instancia con el socket falso ya inyectado (sin conectar)."""
    api = MikroTikAPI(host="test", username="admin", password="secreto")
    api._sock = FakeSocket(rx)
    return api


# ---------------------------------------------------------------------------
# Codificación de longitudes (1–4 bytes)
# ---------------------------------------------------------------------------

class TestLengthEncoding(unittest.TestCase):

    # Casos borde de cada rango del protocolo
    CASES = [
        (0,          b"\x00"),
        (1,          b"\x01"),
        (0x7F,       b"\x7f"),                    # máximo de 1 byte
        (0x80,       b"\x80\x80"),                # mínimo de 2 bytes
        (0x3FFF,     b"\xbf\xff"),                # máximo de 2 bytes
        (0x4000,     b"\xc0\x40\x00"),            # mínimo de 3 bytes
        (0x1FFFFF,   b"\xdf\xff\xff"),            # máximo de 3 bytes
        (0x200000,   b"\xe0\x20\x00\x00"),        # mínimo de 4 bytes
        (0xFFFFFFF,  b"\xef\xff\xff\xff"),
    ]

    def test_send_length_todos_los_rangos(self):
        for length, expected in self.CASES:
            with self.subTest(length=hex(length)):
                api = make_api()
                api._send_length(length)
                self.assertEqual(bytes(api._sock.tx), expected)

    def test_recv_length_todos_los_rangos(self):
        for length, encoded in self.CASES:
            with self.subTest(length=hex(length)):
                api = make_api(rx=encoded)
                self.assertEqual(api._recv_length(), length)

    def test_round_trip_send_recv(self):
        """Lo que _send_length produce, _recv_length lo decodifica."""
        for length in [0, 5, 0x7F, 0x80, 0x1234, 0x3FFF, 0x4000,
                       0x54321, 0x1FFFFF, 0x200000, 0xABCDEF0]:
            with self.subTest(length=hex(length)):
                sender = make_api()
                sender._send_length(length)
                receiver = make_api(rx=bytes(sender._sock.tx))
                self.assertEqual(receiver._recv_length(), length)

    def test_recv_length_socket_cerrado_retorna_cero(self):
        api = make_api(rx=b"")
        self.assertEqual(api._recv_length(), 0)


# ---------------------------------------------------------------------------
# Sentences (words + terminador nulo)
# ---------------------------------------------------------------------------

class TestSentences(unittest.TestCase):

    def test_send_sentence_formato(self):
        api = make_api()
        api._send_sentence(["/system/identity/print"])
        expected = encode_sentence(["/system/identity/print"])
        self.assertEqual(bytes(api._sock.tx), expected)

    def test_recv_sentence_simple(self):
        api = make_api(rx=encode_sentence(["!done"]))
        self.assertEqual(api._recv_sentence(), ["!done"])

    def test_round_trip_sentence_con_utf8(self):
        words = ["/ip/firewall/filter/add",
                 "=comment=CÁMARA-SALA-ÑOÑO",
                 "=action=drop"]
        sender = make_api()
        sender._send_sentence(words)
        receiver = make_api(rx=bytes(sender._sock.tx))
        self.assertEqual(receiver._recv_sentence(), words)

    def test_recv_sentence_word_larga(self):
        """Words > 127 bytes usan prefijo de 2 bytes y deben decodificarse."""
        long_word = "=comment=" + "x" * 300
        api = make_api(rx=encode_sentence([long_word, "!done"]))
        self.assertEqual(api._recv_sentence(), [long_word, "!done"])

    def test_recv_exact_conexion_cerrada(self):
        """Si el socket se queda sin datos a mitad de una word, error claro."""
        api = make_api(rx=b"\x05ab")   # promete 5 bytes, entrega 2
        with self.assertRaises(ConnectionError):
            api._recv_sentence()


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin(unittest.TestCase):

    def test_login_moderno_exitoso(self):
        """RouterOS >= 6.43: /login con password directo → !done."""
        api = make_api(rx=encode_sentence(["!done"]))
        api._login()   # no debe lanzar

        receiver = make_api(rx=bytes(api._sock.tx))
        sent = receiver._recv_sentence()
        self.assertEqual(sent[0], "/login")
        self.assertIn("=name=admin", sent)
        self.assertIn("=password=secreto", sent)

    def _assert_md5_login(self, first_response_words: list, challenge: bytes):
        """Verifica que el cliente complete el challenge MD5 correctamente."""
        rx = (encode_sentence(first_response_words) +
              encode_sentence(["!done"]))
        api = make_api(rx=rx)
        api._login()

        md5 = hashlib.md5()
        md5.update(b"\x00" + "secreto".encode("utf-8") + challenge)
        expected_response = f"=response=00{md5.hexdigest()}"

        receiver = make_api(rx=bytes(api._sock.tx))
        receiver._recv_sentence()                    # primer /login
        second = receiver._recv_sentence()           # /login con response MD5
        self.assertEqual(second[0], "/login")
        self.assertIn("=name=admin", second)
        self.assertIn(expected_response, second)

    def test_login_md5_formato_legacy_real(self):
        """RouterOS < 6.43 responde '!done =ret=<challenge>': aunque venga
        !done, la presencia del challenge obliga a completar el login MD5."""
        challenge = bytes.fromhex("aabbccddeeff00112233445566778899")
        self._assert_md5_login(["!done", f"=ret={challenge.hex()}"], challenge)

    def test_login_md5_challenge_sin_done(self):
        """Variante: challenge sin !done inicial también dispara MD5."""
        challenge = bytes.fromhex("00112233445566778899aabbccddeeff")
        self._assert_md5_login([f"=ret={challenge.hex()}"], challenge)

    def test_login_credenciales_invalidas(self):
        """Respuesta !trap sin challenge → RuntimeError."""
        rx = encode_sentence(["!trap", "=message=invalid user name or password"])
        api = make_api(rx=rx)
        with self.assertRaises(RuntimeError):
            api._login()

    def test_login_md5_segundo_intento_falla(self):
        challenge = bytes.fromhex("00112233445566778899aabbccddeeff")
        rx = (encode_sentence([f"=ret={challenge.hex()}"]) +
              encode_sentence(["!trap", "=message=login failure"]))
        api = make_api(rx=rx)
        with self.assertRaises(RuntimeError):
            api._login()


# ---------------------------------------------------------------------------
# command() — parsing de respuestas
# ---------------------------------------------------------------------------

class TestCommand(unittest.TestCase):

    def test_command_multiples_registros(self):
        rx = (encode_sentence(["!re", "=.id=*1", "=address=192.168.5.10",
                               "=host-name=laptop"]) +
              encode_sentence(["!re", "=.id=*2", "=address=192.168.5.22"]) +
              encode_sentence(["!done"]))
        api = make_api(rx=rx)
        results = api.command("/ip/dhcp-server/lease/print")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["address"], "192.168.5.10")
        self.assertEqual(results[0]["host-name"], "laptop")
        self.assertEqual(results[1][".id"], "*2")

    def test_command_sin_resultados(self):
        api = make_api(rx=encode_sentence(["!done"]))
        self.assertEqual(api.command("/queue/tree/print"), [])

    def test_command_valores_son_strings(self):
        """RouterOS devuelve todo como texto — la lib NO convierte tipos."""
        rx = (encode_sentence(["!re", "=rx-byte=123456", "=running=true"]) +
              encode_sentence(["!done"]))
        api = make_api(rx=rx)
        result = api.command("/interface/print")[0]
        self.assertEqual(result["rx-byte"], "123456")
        self.assertIsInstance(result["rx-byte"], str)
        self.assertEqual(result["running"], "true")

    def test_command_trap_lanza_runtime_error(self):
        rx = encode_sentence(["!trap", "=message=no such command"])
        api = make_api(rx=rx)
        with self.assertRaises(RuntimeError) as ctx:
            api.command("/comando/inexistente")
        self.assertIn("no such command", str(ctx.exception))

    def test_command_envia_params_y_queries(self):
        api = make_api(rx=encode_sentence(["!done"]))
        api.command("/ip/firewall/filter/add",
                    params=["=chain=forward", "=action=drop"],
                    queries=["?src-address=192.168.5.99"])

        receiver = make_api(rx=bytes(api._sock.tx))
        sent = receiver._recv_sentence()
        self.assertEqual(sent, ["/ip/firewall/filter/add",
                                "=chain=forward", "=action=drop",
                                "?src-address=192.168.5.99"])

    def test_command_valor_con_signo_igual(self):
        """Valores que contienen '=' no deben romper el parsing."""
        rx = (encode_sentence(["!re", "=comment=clave=valor=extra"]) +
              encode_sentence(["!done"]))
        api = make_api(rx=rx)
        result = api.command("/ip/firewall/filter/print")[0]
        self.assertEqual(result["comment"], "clave=valor=extra")

    def test_command_raw_retorna_sentences_crudas(self):
        rx = (encode_sentence(["!re", "=name=ether1"]) +
              encode_sentence(["!done"]))
        api = make_api(rx=rx)
        responses = api.command_raw(["/interface/print"])
        self.assertEqual(responses[0], ["!re", "=name=ether1"])
        self.assertEqual(responses[-1], ["!done"])


if __name__ == "__main__":
    unittest.main()
