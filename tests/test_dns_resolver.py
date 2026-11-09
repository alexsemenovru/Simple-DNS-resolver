"""Проверки для dns_resolver: совместимость, форматы, языки, нарезка.

Запуск:  python tests\\test_dns_resolver.py
DNS не используется — getaddrinfo подменяется заглушкой.
"""

import collections
import importlib.util
import io
import ipaddress
import json
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

import i18n  # noqa: E402
import dnsclient  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


new = load("resolver_new", os.path.join(SRC, "dns_resolver.py"))
old = load("resolver_old", os.path.join(ROOT, "recovered", "dns_resolver.py"))

V4_LINE = re.compile(
    r"^route add (?:\d{1,3}\.){3}\d{1,3} mask (?:\d{1,3}\.){3}\d{1,3} "
    r"(?:\d{1,3}\.){3}\d{1,3}$"
)

FAKE_DNS = {
    "a.example": ["1.1.1.1"],
    "b.example": ["1.1.1.1"],
    "c.example": ["2.2.2.2", "3.3.3.3"],
    "v6.example": ["2001:db8::1"],
    "both.example": ["4.4.4.4", "2001:db8::2"],
}


def fake_getaddrinfo(host, port=None, *args, **kwargs):
    if host not in FAKE_DNS:
        raise socket.gaierror(11001, "getaddrinfo failed")
    result = []
    for ip in FAKE_DNS[host]:
        if ":" in ip:
            result.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "",
                           (ip, 0, 0, 0)))
        else:
            result.append((socket.AF_INET, socket.SOCK_STREAM, 6, "",
                           (ip, 0)))
    return result


FORMAT_FLAGS = {"--win", "--unix", "--keenetic", "--keenetic-bat",
                "--mikrotik", "--ovpn", "--wireguard", "--amnezia",
                "--cidr", "--ip"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self._real = socket.getaddrinfo
        socket.getaddrinfo = fake_getaddrinfo
        self._env = os.environ.pop("DNS_RESOLVER_LANG", None)

    def tearDown(self):
        socket.getaddrinfo = self._real
        os.chdir(self.old_cwd)
        self.tmp.cleanup()
        if self._env is not None:
            os.environ["DNS_RESOLVER_LANG"] = self._env

    def write_input(self, lines, name="input.txt"):
        with open(name, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def read(self, name="output.txt"):
        if not os.path.exists(name):
            return b""
        with open(name, "rb") as fh:
            return fh.read()

    def lines(self, name="output.txt"):
        return [l for l in self.read(name).decode("utf-8").splitlines() if l]

    def routes(self, name="output.txt"):
        return collections.Counter(self.lines(name))

    def run_new(self, *argv):
        # По умолчанию проверяем формат win, иначе на Linux умолчанием будет
        # unix и утверждения про "route add" перестанут быть верными.
        arguments = list(argv)
        if not FORMAT_FLAGS & set(arguments):
            arguments = ["--win", *arguments]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = new.main(["-o", "--lang", "ru", *arguments])
        return code, buf.getvalue()

    def run_lang(self, language, *argv):
        arguments = list(argv)
        if not FORMAT_FLAGS & set(arguments):
            arguments = ["--win", *arguments]
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = new.main(["-o", "--lang", language, *arguments])
        return code, buf.getvalue()

    def run_cli(self, *arguments, cwd=None):
        """CLI в отдельном процессе; вывод принудительно в UTF-8.

        На Windows-раннере кодировка консоли не умеет кириллицу, и без этого
        дочерний процесс падал бы на печати справки.
        """
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run(
            [sys.executable, os.path.join(SRC, "dns_resolver.py"), *arguments],
            cwd=cwd or self.tmp.name, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=60, env=env)



class TestLegacyParity(Base):
    """Старый exe и новый код в режиме --no-passthrough должны совпадать.

    Тексты изменились осознанно, поэтому сравниваем после подстановки.
    """

    TEXT_MAP = {
        "Попытка разрешить адрес: ": "Ищу IP домена: ",
    }

    def normalize(self, text):
        for old_text, new_text in self.TEXT_MAP.items():
            text = text.replace(old_text, new_text)
        return text

    def test_stdout_and_files_identical(self):
        self.write_input([
            "a.example", "c.example", "v6.example", "both.example",
            "missing.example", "91.108.4.0/22", "http://d.example:8443/path",
            "", "_bad.example", "b.example",
        ])

        buf = io.StringIO()
        with redirect_stdout(buf):
            old.resolve_and_write_routes()
        old_stdout = self.normalize(buf.getvalue())
        old_routes = self.read()
        old_v6 = self.read("output-IPv6.txt")

        code, new_stdout = self.run_new("--no-passthrough", "--jobs", "1")

        self.assertEqual(code, 0)
        self.assertEqual(old_stdout, new_stdout)
        self.assertEqual(old_routes, self.read("output.txt"))
        self.assertEqual(old_v6, self.read("output-IPv6.txt"))

    def test_missing_input(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            old.resolve_and_write_routes()
        old_stdout = buf.getvalue()

        code, new_stdout = self.run_new("--no-passthrough")

        self.assertEqual(old_stdout, new_stdout)
        self.assertEqual(code, 1)

    def test_empty_input(self):
        self.write_input(["", "   "])
        buf = io.StringIO()
        with redirect_stdout(buf):
            old.resolve_and_write_routes()
        old_stdout = buf.getvalue()

        code, new_stdout = self.run_new("--no-passthrough")
        self.assertEqual(old_stdout, new_stdout)
        self.assertEqual(code, 0)

    def test_order_is_preserved_with_threads(self):
        self.write_input(["a.example", "c.example", "v6.example",
                          "both.example"])
        code, out = self.run_new("--jobs", "8")
        positions = [out.index(f"Ищу IP домена: {h}")
                     for h in ("a.example", "c.example", "v6.example",
                               "both.example")]
        self.assertEqual(positions, sorted(positions))


class TestFormat(Base):
    def test_every_line_matches_and_crlf_no_bom(self):
        self.write_input(["a.example", "c.example", "v6.example", "8.8.8.0/24"])
        code, _ = self.run_new("--modern")
        self.assertEqual(code, 0)

        raw = self.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), "BOM недопустим")
        self.assertEqual(raw.count(b"\n"), raw.count(new.EOL.encode()), "переводы строк как в системе")
        self.assertTrue(raw.endswith(new.EOL.encode()))
        self.assertNotIn(b"  ", raw.replace(new.EOL.encode(), b""))

        for line in self.lines():
            self.assertRegex(line, V4_LINE)

    def test_no_trailing_blank_lines(self):
        self.write_input(["a.example"])
        self.run_new("--modern")
        self.assertEqual(self.read(),
                         ("route add 1.1.1.1 mask 255.255.255.255 0.0.0.0" + new.EOL).encode())


class TestDedup(Base):
    def test_legacy_mode_keeps_duplicates(self):
        self.write_input(["a.example", "b.example"])
        self.run_new()
        self.assertEqual(sum(self.routes().values()), 2)

    def test_dedup_flag_collapses(self):
        self.write_input(["a.example", "b.example"])
        code, out = self.run_new("--dedup")
        self.assertEqual(code, 0)
        self.assertEqual(self.routes(), collections.Counter(
            {"route add 1.1.1.1 mask 255.255.255.255 0.0.0.0": 1}))
        self.assertIn("Повторов убрано: 1", out)

    def test_dedup_sort_is_stable(self):
        self.write_input(["c.example", "a.example"])
        self.run_new("--dedup", "--sort")
        first = self.read()
        self.run_new("--dedup", "--sort")
        self.assertEqual(first, self.read())
        self.assertEqual(self.lines(), sorted(self.lines()))


class TestPassthrough(Base):
    def test_ip_passthrough_is_default(self):
        self.write_input(["1.2.3.4"])
        code, out = self.run_new()
        self.assertEqual(code, 0)
        self.assertIn("Это уже IP — переношу: 1.2.3.4", out)
        self.assertEqual(self.read(),
                         ("route add 1.2.3.4 mask 255.255.255.255 0.0.0.0"
                          + new.EOL).encode())

    def test_subnet_message(self):
        self.write_input(["91.108.4.0/22"])
        code, out = self.run_new()
        self.assertEqual(code, 0)
        self.assertIn("Это уже подсеть — переношу: 91.108.4.0/22", out)
        self.assertIn("route add 91.108.4.0 mask 255.255.252.0 0.0.0.0",
                      self.lines())

    def test_cidr_gets_mask(self):
        self.write_input(["91.108.4.0/22", "185.76.151.0/24", "8.8.8.8/32"])
        code, _ = self.run_new("--modern")
        self.assertEqual(code, 0)
        lines = self.lines()
        self.assertIn("route add 91.108.4.0 mask 255.255.252.0 0.0.0.0", lines)
        self.assertIn("route add 185.76.151.0 mask 255.255.255.0 0.0.0.0", lines)
        self.assertIn("route add 8.8.8.8 mask 255.255.255.255 0.0.0.0", lines)

    def test_no_passthrough_rejects_cidr(self):
        self.write_input(["91.108.4.0/22"])
        code, out = self.run_new("--no-passthrough")
        self.assertEqual(code, 0)
        self.assertIn("Некорректный формат адреса: 91.108.4.0/22", out)
        self.assertEqual(self.read(), b"")

    def test_no_passthrough_resolves_bare_ip(self):
        self.write_input(["1.2.3.4"])
        code, out = self.run_new("--no-passthrough")
        self.assertEqual(code, 0)
        self.assertIn("Ищу IP домена: 1.2.3.4", out)
        self.assertEqual(self.read(), b"")

    def test_ipv6_literal(self):
        self.write_input(["2001:db8::1"])
        code, _ = self.run_new()
        self.assertEqual(code, 0)
        self.assertEqual(self.read("output-IPv6.txt").decode(),
                         "route -p add 2001:db8::1/128 interface=0" + new.EOL)

    def test_dangerous_default_route_skipped(self):
        self.write_input(["0.0.0.0/0", "a.example"])
        code, out = self.run_new("--modern")
        self.assertEqual(code, 0)
        self.assertIn("Пропущен непригодный для маршрута адрес: 0.0.0.0/0", out)
        self.assertEqual(len(self.routes()), 1)

    def test_wide_route_warns_but_kept(self):
        self.write_input(["1.0.0.0/8"])
        code, out = self.run_new("--modern")
        self.assertEqual(code, 0)
        self.assertIn("Слишком широкий маршрут", out)
        self.assertIn("route add 1.0.0.0 mask 255.0.0.0 0.0.0.0", self.lines())


class TestFormats(Base):
    def fmt_lines(self, *argv):
        code, _ = self.run_new("--modern", *argv)
        self.assertEqual(code, 0)
        return self.lines()

    def test_explicit_win(self):
        self.write_input(["a.example"])
        self.assertEqual(self.fmt_lines("--win"),
                         ["route add 1.1.1.1 mask 255.255.255.255 0.0.0.0"])

    def test_default_format_is_platform_native(self):
        self.write_input(["1.2.3.4"])
        proc = self.run_cli("--lang", "ru", "-o")
        self.assertEqual(proc.returncode, 0)
        first = self.lines()[0]
        prefix = "route add " if os.name == "nt" else "ip route add "
        self.assertTrue(first.startswith(prefix), first)

    def test_unix(self):
        self.write_input(["a.example", "8.8.8.0/24"])
        self.assertEqual(self.fmt_lines("--unix", "--gateway", "10.0.0.1"), [
            "ip route add 1.1.1.1/32 via 10.0.0.1",
            "ip route add 8.8.8.0/24 via 10.0.0.1",
        ])

    def test_unix_without_gateway_uses_dev(self):
        self.write_input(["a.example"])
        self.assertEqual(self.fmt_lines("--unix", "--interface", "wg0"),
                         ["ip route add 1.1.1.1/32 dev wg0"])

    def test_keenetic(self):
        self.write_input(["a.example", "91.108.4.0/22"])
        self.assertEqual(
            self.fmt_lines("--keenetic", "--gateway", "10.0.0.1",
                           "--interface", "Wireguard0", "--comment", "telegram"),
            [
                "ip route 1.1.1.1/32 10.0.0.1 Wireguard0 auto !telegram",
                "ip route 91.108.4.0/22 10.0.0.1 Wireguard0 auto !telegram",
            ])

    def test_keenetic_bat_uses_own_template(self):
        self.write_input(["a.example", "91.108.4.0/22"])
        code, _ = self.run_new("--modern", "--keenetic-bat", "--no-chunk")
        self.assertEqual(code, 0)
        self.assertEqual(self.lines("output.bat"), [
            "route add 1.1.1.1 mask 255.255.255.255 0.0.0.0",
            "route add 91.108.4.0 mask 255.255.252.0 0.0.0.0",
        ])

    def test_keenetic_bat_extension(self):
        self.write_input(["a.example"])
        self.run_new("--modern", "--keenetic-bat", "--no-chunk")
        self.assertTrue(os.path.exists("output.bat"))
        self.assertFalse(os.path.exists("output.txt"))

    def test_keenetic_bat_chunks_by_999(self):
        lines = [f"10.{i // 256}.{i % 256}.0/24" for i in range(1000)]
        self.write_input(lines)
        code, out = self.run_new("--modern", "--keenetic-bat")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists("output_p1.bat"))
        self.assertTrue(os.path.exists("output_p2.bat"))
        self.assertFalse(os.path.exists("output.bat"))
        self.assertEqual(len(self.read("output_p1.bat").decode().splitlines()), 999)
        self.assertEqual(len(self.read("output_p2.bat").decode().splitlines()), 1)
        self.assertIn("output_p1.bat", out)

    def test_mikrotik(self):
        self.write_input(["a.example"])
        self.assertEqual(
            self.fmt_lines("--mikrotik", "--list", "vpn",
                           "--comment", "telegram"),
            ['/ip/firewall/address-list add list=vpn comment="telegram" '
             'address=1.1.1.1/32'])

    def test_mikrotik_without_comment(self):
        self.write_input(["a.example"])
        self.assertEqual(
            self.fmt_lines("--mikrotik", "--list", "work"),
            ["/ip/firewall/address-list add list=work address=1.1.1.1/32"])

    def test_ovpn(self):
        self.write_input(["a.example", "8.8.8.0/24"])
        self.assertEqual(self.fmt_lines("--ovpn"), [
            'push "route 1.1.1.1 255.255.255.255"',
            'push "route 8.8.8.0 255.255.255.0"',
        ])

    def test_cidr(self):
        self.write_input(["a.example", "91.108.4.0/22"])
        self.assertEqual(self.fmt_lines("--cidr"), ["1.1.1.1/32", "91.108.4.0/22"])

    def test_ip_format(self):
        self.write_input(["a.example", "91.108.4.0/22"])
        self.assertEqual(self.fmt_lines("--ip"), ["1.1.1.1", "91.108.4.0"])

    def test_wireguard_single_line(self):
        self.write_input(["c.example", "a.example"])
        self.assertEqual(self.fmt_lines("--wireguard"),
                         ["1.1.1.1/32, 2.2.2.2/32, 3.3.3.3/32"])

    def test_amnezia_json(self):
        self.write_input(["a.example", "91.108.4.0/22"])
        code, _ = self.run_new("--modern", "--amnezia")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists("output.json"))
        data = json.loads(self.read("output.json").decode("utf-8"))
        self.assertEqual(data, [
            {"hostname": "1.1.1.1/32", "ip": ""},
            {"hostname": "91.108.4.0/22", "ip": ""},
        ])

    def test_formats_are_mutually_exclusive(self):
        self.write_input(["a.example"])
        proc = self.run_cli("--cidr", "--keenetic")
        self.assertNotEqual(proc.returncode, 0)

    def test_default_format_depends_on_platform(self):
        self.assertEqual(new.DEFAULT_FORMAT, "win" if os.name == "nt" else "unix")

    def test_unix_ipv6_uses_ip6(self):
        self.write_input(["v6.example"])
        code, _ = self.run_new("--modern", "--unix")
        self.assertEqual(code, 0)
        self.assertEqual(self.read("output-IPv6.txt").decode(),
                         "ip -6 route add 2001:db8::1/128" + new.EOL)

    def test_ipv6_stays_in_separate_file(self):
        self.write_input(["v6.example", "a.example"])
        self.run_new("--modern", "--cidr")
        self.assertEqual(self.lines(), ["1.1.1.1/32"])
        self.assertEqual(self.read("output-IPv6.txt").decode(),
                         "2001:db8::1/128" + new.EOL)


class TestStrictValidation(Base):
    def test_bad_mask_detected(self):
        record = new.RouteRecord(4, new.ipaddress.ip_network("8.8.8.0/24"))
        record.line = "route add 8.8.8.0 mask 255.255.255.255 0.0.0.0"

        class S:
            format = "win"
            gateway = "0.0.0.0"

        with self.assertRaises(ValueError):
            new.validate_records([record], S())

    def test_double_space_detected(self):
        record = new.RouteRecord(4, new.ipaddress.ip_network("1.1.1.1/32"))
        record.line = "route add  1.1.1.1 mask 255.255.255.255 0.0.0.0"

        class S:
            format = "win"
            gateway = "0.0.0.0"

        with self.assertRaises(ValueError):
            new.validate_records([record], S())

    def test_good_line_passes(self):
        record = new.RouteRecord(4, new.ipaddress.ip_network("1.1.1.1/32"))
        record.line = "route add 1.1.1.1 mask 255.255.255.255 0.0.0.0"

        class S:
            format = "win"
            gateway = "0.0.0.0"

        self.assertTrue(new.validate_records([record], S()))


class TestRetries(Base):
    """Домашний роутер может ответить отказом под нагрузкой — нужен повтор."""

    def test_retry_after_transient_failure(self):
        calls = {"n": 0}

        def flaky(host, port=None, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise socket.gaierror(11002, "temporary failure")
            return fake_getaddrinfo(host, port)

        socket.getaddrinfo = flaky
        self.write_input(["a.example"])
        code, _ = self.run_new("--retries", "2", "--jobs", "1")
        self.assertEqual(code, 0)
        self.assertIn("1.1.1.1", self.read().decode())
        self.assertGreaterEqual(calls["n"], 2)

    def test_single_attempt_reports_error(self):
        def always_fail(host, port=None, *args, **kwargs):
            raise socket.gaierror(11001, "getaddrinfo failed")

        socket.getaddrinfo = always_fail
        self.write_input(["a.example"])
        code, out = self.run_new("--retries", "1", "--jobs", "1")
        self.assertEqual(code, 0)
        self.assertIn("Не удалось разрешить имя хоста: a.example", out)
        self.assertEqual(self.read(), b"")


def udp_loopback_works():
    """В некоторых песочницах (и в этой WSL) UDP на loopback не доставляется."""
    receiver = sender = None
    try:
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(0.5)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.sendto(b"probe", receiver.getsockname())
        receiver.recvfrom(16)
        return True
    except OSError:
        return False
    finally:
        for sock in (receiver, sender):
            if sock is not None:
                sock.close()


UDP_LOOPBACK = udp_loopback_works()


class FakeDns(threading.Thread):
    """Крошечный UDP-сервер DNS для тестов: отвечает по словарю zone."""

    def __init__(self, zone, rcode=0):
        super().__init__(daemon=True)
        self.zone = {name.lower(): ips for name, ips in zone.items()}
        self.rcode = rcode
        self.queries = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]

    def run(self):
        while True:
            try:
                data, address = self.sock.recvfrom(512)
            except OSError:
                return
            self.queries += 1
            response = self.build(data)
            if response:
                self.sock.sendto(response, address)

    def build(self, query):
        if len(query) < 12:
            return None
        query_id, _, _, _, _, _ = struct.unpack("!HHHHHH", query[:12])
        name, offset = dnsclient.read_name(query, 12)
        qtype, _ = struct.unpack("!HH", query[offset:offset + 4])
        question = query[12:offset + 4]

        key = name.lower()
        rcode = self.rcode
        records = []

        if rcode == 0:
            if key not in self.zone:
                rcode = 3
            else:
                for ip in self.zone[key]:
                    address = ipaddress.ip_address(ip)
                    if qtype == 1 and address.version == 4:
                        rtype, rdata = 1, address.packed
                    elif qtype == 28 and address.version == 6:
                        rtype, rdata = 28, address.packed
                    else:
                        continue
                    records.append(struct.pack("!HHHIH", 0xC00C, rtype, 1, 60,
                                               len(rdata)) + rdata)

        flags = 0x8180 | rcode
        header = struct.pack("!HHHHHH", query_id, flags, 1, len(records), 0, 0)
        return header + question + b"".join(records)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


@unittest.skipUnless(UDP_LOOPBACK,
                     "UDP на loopback недоступен в этом окружении")
class TestCustomDns(Base):
    """--dns: спрашивать конкретный сервер, а не системный резолвер."""

    def start_server(self, zone, rcode=0):
        server = FakeDns(zone, rcode)
        server.start()
        self.addCleanup(server.close)
        return server

    def test_resolves_a_record(self):
        server = self.start_server({"a.example": ["5.6.7.8"]})
        self.write_input(["a.example"])

        def must_not_be_used(*args, **kwargs):
            raise AssertionError("системный резолвер использован быть не должен")

        socket.getaddrinfo = must_not_be_used

        code, out = self.run_new("--dns", f"127.0.0.1:{server.port}")
        self.assertEqual(code, 0)
        self.assertIn("route add 5.6.7.8 mask 255.255.255.255 0.0.0.0",
                      self.lines())
        self.assertIn("DNS-серверы: 127.0.0.1:", out)

    def test_resolves_aaaa_record(self):
        server = self.start_server({"v6.example": ["2001:db8::5"]})
        self.write_input(["v6.example"])
        code, _ = self.run_new("--dns", f"127.0.0.1:{server.port}")
        self.assertEqual(code, 0)
        self.assertEqual(self.read("output-IPv6.txt").decode(),
                         "route -p add 2001:db8::5/128 interface=0" + new.EOL)

    def test_nxdomain_means_no_addresses(self):
        server = self.start_server({}, rcode=0)
        self.write_input(["missing.example"])
        code, out = self.run_new("--dns", f"127.0.0.1:{server.port}",
                                 "--retries", "1")
        self.assertEqual(code, 0)
        self.assertIn("не найдено IP адресов", out)
        self.assertEqual(self.read(), b"")

    def test_dead_server_reports_error(self):
        self.write_input(["a.example"])
        code, out = self.run_new("--dns", "127.0.0.1:9", "--dns-timeout", "0.3",
                                 "--retries", "1")
        self.assertEqual(code, 0)
        self.assertIn("Не удалось разрешить имя хоста: a.example", out)

    def test_second_server_used_when_first_is_dead(self):
        server = self.start_server({"a.example": ["9.9.9.9"]})
        self.write_input(["a.example"])
        code, _ = self.run_new("--dns", "127.0.0.1:9",
                               "--dns", f"127.0.0.1:{server.port}",
                               "--dns-timeout", "0.5", "--retries", "1")
        self.assertEqual(code, 0)
        self.assertIn("route add 9.9.9.9 mask 255.255.255.255 0.0.0.0",
                      self.lines())

    def test_ip_and_cidr_do_not_touch_dns(self):
        server = self.start_server({})
        self.write_input(["1.2.3.4", "91.108.4.0/22"])
        code, _ = self.run_new("--dns", f"127.0.0.1:{server.port}")
        self.assertEqual(code, 0)
        self.assertEqual(server.queries, 0)
        self.assertEqual(len(self.lines()), 2)

    def test_invalid_server_rejected(self):
        self.write_input(["a.example"])
        code, out = self.run_new("--dns", "not-an-ip")
        self.assertEqual(code, 2)
        self.assertIn("Некорректный DNS-сервер", out)


class TestDnsProtocol(unittest.TestCase):
    """Разбор пакетов — без сети."""

    def test_parse_servers(self):
        self.assertEqual(dnsclient.parse_servers(["1.1.1.1"]), [("1.1.1.1", 53)])
        self.assertEqual(dnsclient.parse_servers(["8.8.8.8:5353"]),
                         [("8.8.8.8", 5353)])
        self.assertEqual(dnsclient.parse_servers(["1.1.1.1,8.8.8.8"]),
                         [("1.1.1.1", 53), ("8.8.8.8", 53)])
        self.assertEqual(dnsclient.parse_servers(["[2001:db8::1]:53"]),
                         [("2001:db8::1", 53)])
        with self.assertRaises(ValueError):
            dnsclient.parse_servers(["999.1.1.1"])

    def test_truncated_flag_detected(self):
        query = dnsclient.build_query("a.example", dnsclient.QTYPE_A, 7)
        response = struct.pack("!HHHHHH", 7, 0x8380, 0, 0, 0, 0) + query[12:]
        rcode, truncated, addresses, _ = dnsclient.parse_response(response, 7)
        self.assertTrue(truncated)
        self.assertEqual(rcode, 0)
        self.assertEqual(addresses, [])

    def test_wrong_id_rejected(self):
        query = dnsclient.build_query("a.example", dnsclient.QTYPE_A, 7)
        response = struct.pack("!HHHHHH", 8, 0x8180, 0, 0, 0, 0) + query[12:]
        with self.assertRaises(dnsclient.DnsError):
            dnsclient.parse_response(response, 7)

    def test_compression_pointer_loop_guard(self):
        data = b"\xc0\x0c" + b"\x00" * 10  # указатель сам на себя
        with self.assertRaises(dnsclient.DnsError):
            dnsclient.read_name(data, 0)

    def test_name_roundtrip(self):
        self.assertEqual(dnsclient.encode_name("a.b.example"),
                         b"\x01a\x01b\x07example\x00")


class TestLanguage(Base):
    def test_english(self):
        self.write_input(["a.example"])
        code, out = self.run_lang("en")
        self.assertEqual(code, 0)
        self.assertIn("Read 1 targets from file", out)
        self.assertIn("Looking up IP for domain: a.example", out)
        self.assertIn("IPv4 addresses for a.example: 1.1.1.1", out)

    def test_spanish(self):
        self.write_input(["a.example"])
        _, out = self.run_lang("es")
        self.assertIn("Leídos 1 destinos del archivo", out)
        self.assertIn("Busco la IP del dominio: a.example", out)

    def test_chinese(self):
        self.write_input(["a.example"])
        _, out = self.run_lang("zh")
        self.assertIn("已从文件读取 1 个目标", out)
        self.assertIn("正在查找域名 IP：a.example", out)

    def test_russian(self):
        self.write_input(["a.example"])
        _, out = self.run_lang("ru")
        self.assertIn("Прочитано 1 адресов из файла", out)

    def test_environment_variable(self):
        os.environ["DNS_RESOLVER_LANG"] = "es"
        self.assertEqual(i18n.detect_language(), "es")

    def test_normalize(self):
        self.assertEqual(i18n.normalize_language("ru-RU"), "ru")
        self.assertEqual(i18n.normalize_language("zh_CN.UTF-8"), "zh")
        self.assertEqual(i18n.normalize_language("de-DE"), None)

    def test_all_languages_have_every_key(self):
        for key, entry in i18n.CATALOG.items():
            for language in i18n.LANGUAGES:
                self.assertIn(language, entry, f"{key} без {language}")

    def test_placeholders_match_across_languages(self):
        pattern = re.compile(r"\{(\w+)\}")
        for key, entry in i18n.CATALOG.items():
            base = set(pattern.findall(entry["en"]))
            for language in i18n.LANGUAGES:
                self.assertEqual(base, set(pattern.findall(entry[language])),
                                 f"{key}: {language}")


class TestPathsAndPause(Base):
    """-o: создаёт папки и снимает паузу; без значения — путь по умолчанию."""

    def test_nested_output_dir_is_created(self):
        self.write_input(["1.2.3.4"])
        target = os.path.join("sub", "deeper", "out.txt")
        code, _ = self.run_new("-o", target)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(target))
        self.assertEqual(self.lines(target),
                         ["route add 1.2.3.4 mask 255.255.255.255 0.0.0.0"])

    def test_ipv6_output_dir_is_created(self):
        self.write_input(["2001:db8::1"])
        target = os.path.join("v6dir", "nested", "v6.txt")
        code, _ = self.run_new("--ipv6-output", target)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(target))

    def test_dash_o_without_value_keeps_default_name(self):
        self.write_input(["1.2.3.4"])
        code, out = self.run_new("-o")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists("output.txt"))
        self.assertNotIn("Enter", out)

    def test_pause_depends_on_output_flag(self):
        class Tty(io.StringIO):
            def isatty(self):
                return True

        parser = new.build_parser("ru")
        original = new.sys.stdin
        try:
            new.sys.stdin = Tty()
            self.assertTrue(new.Settings(parser.parse_args([]), "ru").pause)
            self.assertFalse(new.Settings(parser.parse_args(["-o"]), "ru").pause)
            self.assertFalse(
                new.Settings(parser.parse_args(["-o", ""]), "ru").pause)
            self.assertFalse(
                new.Settings(parser.parse_args(["--ipv6-output", "x.txt"]),
                             "ru").pause)
        finally:
            new.sys.stdin = original

    def test_empty_value_means_default_path(self):
        parser = new.build_parser("ru")
        settings = new.Settings(parser.parse_args(["-o", ""]), "ru")
        self.assertEqual(settings.output_path, new.DEFAULT_OUTPUT)


class TestCli(Base):
    def test_help_lists_formats(self):
        proc = self.run_cli("--lang", "ru", "--help")
        text = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, 0)
        for name in ("--win", "--amnezia", "--keenetic-bat", "--ip"):
            self.assertIn(name, text)
        self.assertIn("коды возврата", text)

    def test_slash_question_works(self):
        proc = self.run_cli("/?", "--lang", "ru")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("форматы", proc.stdout.decode("utf-8"))

    def test_help_in_english(self):
        proc = self.run_cli("--lang", "en", "--help")
        self.assertIn("exit codes", proc.stdout.decode("utf-8"))

    def test_no_wait_without_tty(self):
        self.write_input(["a.example"])
        proc = self.run_cli("-o")
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn(b"Enter", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
