#!/usr/bin/env python3
"""dns_resolver — домены/IP/CIDR → маршруты.

Работает на Windows и Linux. Без флагов выдаёт простой список маршрутов IPv4
в формате, родном для текущей системы (win на Windows, unix на Linux),
с прежними правилами разбора и прежним форматом файла.

  * --modern — пресет: дедупликация, стабильный порядок и строгая проверка;
  * --no-passthrough — гонять IP через DNS, как делали старые версии.

Готовые IP и подсети по умолчанию переносятся напрямую, без DNS.

Форматы вывода (по мотивам DomainMapper): --win, --unix, --keenetic,
--keenetic-bat, --mikrotik, --ovpn, --wireguard, --amnezia, --cidr, --ip.
Префикс всегда берётся из самой сети: /32 для одиночного IP, /22 для CIDR.

Язык интерфейса — системный, ключ --lang или переменная DNS_RESOLVER_LANG.
Зависимостей нет, только стандартная библиотека.
"""

import argparse
import bisect
import ipaddress
import os
import re
import socket
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import i18n
import dnsclient

VERSION = "3.5.0"

# Потолок параллельных запросов: защита от случайного OOM, а не от атаки.
MAX_JOBS = 256


class RateLimiter:
    """Общий на все потоки ограничитель: не больше N запросов в секунду.

    Держит равномерный темп без пачек: каждый следующий запрос ждёт своей
    очереди. Именно это спасает слабые домашние роутеры — параллельность
    сама по себе пик не ограничивает.
    """

    def __init__(self, per_second):
        self.interval = 1.0 / per_second if per_second > 0 else 0.0
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def acquire(self):
        if not self.interval:
            return
        with self.lock:
            now = time.monotonic()
            wait = self.next_slot - now
            if wait < 0:
                wait = 0.0
            self.next_slot = max(now, self.next_slot) + self.interval
        if wait > 0:
            time.sleep(wait)

# Три состояния ключа пути: не указан, указан без значения, указан со значением.
UNSET = object()
NO_VALUE = object()

# Windows-файлы вставляют в .bat, там нужен CRLF; на Linux — обычный LF.
EOL = "\r\n" if os.name == "nt" else "\n"

DEFAULT_OUTPUT = "output.txt"
DEFAULT_IPV6_OUTPUT = "output-IPv6.txt"

# Без флага — формат, родной для системы.
DEFAULT_FORMAT = "win" if os.name == "nt" else "unix"


class FormatSpec:
    """Описание формата вывода и параметров, которые ему нужны."""

    __slots__ = ("name", "example_key", "separator", "header", "footer",
                 "extension", "chunk", "needs")

    def __init__(self, name, example_key, separator=EOL, header="",
                 footer="", extension=None, chunk=None, needs=()):
        self.name = name
        self.example_key = example_key
        self.separator = separator
        self.header = header
        self.footer = footer
        self.extension = extension
        self.chunk = chunk
        self.needs = needs


FORMAT_SPECS = OrderedDict([
    ("win", FormatSpec("win", "f_win", needs=("gateway",))),
    ("unix", FormatSpec("unix", "f_unix", needs=("gateway",))),
    ("keenetic", FormatSpec("keenetic", "f_keenetic",
                            needs=("gateway", "interface", "comment"))),
    ("keenetic-bat", FormatSpec("keenetic-bat", "f_keenetic_bat",
                                extension=".bat", chunk=999)),
    ("mikrotik", FormatSpec("mikrotik", "f_mikrotik",
                            needs=("list", "comment"))),
    ("ovpn", FormatSpec("ovpn", "f_ovpn")),
    ("wireguard", FormatSpec("wireguard", "f_wireguard", separator=", ")),
    ("amnezia", FormatSpec("amnezia", "f_amnezia", separator="," + EOL,
                           header="[" + EOL, footer=EOL + "]" + EOL,
                           extension=".json")),
    ("cidr", FormatSpec("cidr", "f_cidr")),
    ("ip", FormatSpec("ip", "f_ip")),
])

FORMATS = tuple(FORMAT_SPECS)

# Строгие шаблоны для проверки готовых строк.
V4_LINE_RE = re.compile(
    r"^route (?:-p )?add (?:\d{1,3}\.){3}\d{1,3} mask (?:\d{1,3}\.){3}\d{1,3} "
    r"(?:\d{1,3}\.){3}\d{1,3}$"
)
V6_LINE_RE = re.compile(r"^route -p add [0-9A-Fa-f:]+/\d{1,3} interface=\d+$")

HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9.-]+$")

IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?$")
IPV6_RE = re.compile(r"^[0-9A-Fa-f:]*:[0-9A-Fa-f:.]*(?:/\d{1,3})?$")

USELESS_V4 = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
]


def path_or_default(value, default):
    """Ключ без значения или с пустым значением — это путь по умолчанию."""
    if value is UNSET or value is NO_VALUE or value == "":
        return default
    return value


class Coverage:
    """Сколько адресов из набора покрыто диапазоном — быстро, по интервалам."""

    def __init__(self, intervals):
        self.intervals = intervals
        self.ends = [end for _, end in intervals]
        self.before_ = []
        total = 0
        for start, end in intervals:
            self.before_.append(total)
            total += end - start
        self.total = total

    def covered_before(self, point):
        index = bisect.bisect_right(self.ends, point)
        if index >= len(self.intervals):
            return self.total
        total = self.before_[index]
        start, _ = self.intervals[index]
        if start < point:
            total += point - start
        return total

    def count(self, low, high):
        return self.covered_before(high) - self.covered_before(low)


def to_intervals(records):
    """Объединяет сети в непересекающиеся интервалы адресов."""
    spans = sorted(
        (int(record.network.network_address),
         int(record.network.network_address) + record.network.num_addresses)
        for record in records
        if record.network.num_addresses
    )
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def walk_blocks(coverage, low, prefix, bits, max_prefix, budget, out, exact):
    """Дерево префиксов: сливаем в блок, если он не крупнее max_prefix.

    budget — сколько адресов, которых не было в списке, допускается «прихватить».
    При budget = 0 сливаются только полностью покрытые блоки (свёртка без потерь).
    Блок, который уже был во входе, никогда не дробится — свёртка только укрупняет.
    """
    size = 1 << (bits - prefix)
    count = coverage.count(low, low + size)
    if count == 0:
        return

    if (low, prefix) in exact:
        out.append((low, prefix))
        return

    if prefix >= max_prefix and size - count <= budget:
        out.append((low, prefix))
        return

    if prefix >= bits:
        out.append((low, bits))
        return

    half = size >> 1
    walk_blocks(coverage, low, prefix + 1, bits, max_prefix, budget, out, exact)
    walk_blocks(coverage, low + half, prefix + 1, bits, max_prefix, budget, out,
                exact)


def aggregate_records(records, settings):
    """Свёртка маршрутов в подсети. Область покрытия не сужается."""
    if not records:
        return records

    family = records[0].family
    if family == 4:
        bits, max_prefix = 32, min(max(settings.aggregate_max, 0), 32)
        factory = ipaddress.IPv4Network
    else:
        bits, max_prefix = 128, min(max(settings.aggregate_max_v6, 0), 128)
        factory = ipaddress.IPv6Network

    coverage = Coverage(to_intervals(records))
    exact = {(int(record.network.network_address), record.network.prefixlen)
             for record in records}
    blocks = []
    walk_blocks(coverage, 0, 0, bits, max_prefix, settings.aggregate_budget,
                blocks, exact)

    aggregated = []
    for low, prefix in blocks:
        record = RouteRecord(family, factory((low, prefix)))
        record.line = format_record(record, settings)
        aggregated.append(record)
    return aggregated


class Settings:
    """Все настройки прогона в одном месте."""

    def __init__(self, args, language):
        self.language = language
        self.input_path = args.input

        # Путь вывода: ключ без значения означает «путь по умолчанию, но без
        # паузы в конце» — так можно получить неинтерактивный запуск, не
        # меняя имён файлов.
        self.output_path = path_or_default(args.output, DEFAULT_OUTPUT)
        self.ipv6_output_path = path_or_default(args.ipv6_output,
                                                DEFAULT_IPV6_OUTPUT)
        self.unattended = (args.output is not UNSET
                           or args.ipv6_output is not UNSET)

        self.format = args.format or DEFAULT_FORMAT
        self.gateway = args.gateway
        self.interface = args.interface
        self.list_name = args.list
        self.comment = args.comment
        self.iface = args.iface

        requested_jobs = max(1, args.jobs)
        self.jobs = min(requested_jobs, MAX_JOBS)
        self.jobs_capped = requested_jobs > MAX_JOBS

        self.qps = max(0, args.qps)
        self.limiter = RateLimiter(self.qps) if self.qps else None
        self.retries = max(1, args.retries)
        self.dns_servers = dnsclient.parse_servers(args.dns)
        self.dns_timeout = max(0.1, args.dns_timeout)
        self.passthrough = args.passthrough
        self.persistent = args.persistent
        # Повторы не нужны никогда: схлопываем их всегда, без возможности
        # отключить — иначе на выходе снова тысячи лишних строк.
        self.dedup = True

        # Свёртка в подсети. Без ключа — точная (без «лишних» адресов).
        # Явный --aggregate-budget 0 выключает свёртку совсем.
        budget = args.aggregate_budget
        if budget is UNSET:
            self.aggregate_enabled = True
            self.aggregate_budget = 0
        else:
            self.aggregate_budget = max(0, budget)
            self.aggregate_enabled = self.aggregate_budget > 0
        self.aggregate_max = args.aggregate_max
        self.aggregate_max_v6 = args.aggregate_max_v6
        self.sort = args.sort or args.modern
        self.strict = args.strict or args.modern
        self.modern = args.modern or args.strict
        self.chunk = not args.no_chunk

        self.pause = (not self.unattended) and sys.stdin is not None \
            and sys.stdin.isatty()

    def spec(self):
        return FORMAT_SPECS[self.format]

    def say(self, key, **values):
        return i18n.translate(self.language, key, **values)


class RouteRecord:
    """Один будущий маршрут: сеть + семья. Строка строится форматом."""

    __slots__ = ("family", "network", "line")

    def __init__(self, family, network):
        self.family = family
        self.network = network
        self.line = ""

    def sort_key(self):
        return (self.family, int(self.network.network_address),
                self.network.prefixlen)


class Outcome:
    """Результат обработки одной входной строки."""

    __slots__ = ("kind", "value", "host", "network", "ipv4", "ipv6",
                 "records", "error")

    def __init__(self, kind, value, host=None, network=None, ipv4=(),
                 ipv6=(), records=(), error=None):
        self.kind = kind
        self.value = value
        self.host = host
        self.network = network
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.records = list(records)
        self.error = error


# --- legacy-функции: восстановлены из байткода, менять их нельзя ------------


def clean_hostname(url):
    """Достаёт имя хоста из строки, которая может быть URL."""
    try:
        if "//" in url:
            parsed = urlparse(url if "://" in url else f"http://{url}")
            hostname = parsed.netloc
        else:
            hostname = url

        hostname = hostname.split(":")[0]
        hostname = hostname.strip()

        if HOSTNAME_RE.match(hostname):
            return hostname
        return None
    except Exception:
        return None


def get_all_ip_addresses(hostname):
    """Резолвит имя через системный резолвер: (список IPv4, список IPv6)."""
    try:
        addrinfo = socket.getaddrinfo(hostname, None)

        ipv4_addresses = set()
        ipv6_addresses = set()

        for addr in addrinfo:
            if addr[0] == socket.AF_INET:
                ipv4_addresses.add(addr[4][0])
            elif addr[0] == socket.AF_INET6:
                ipv6_addresses.add(addr[4][0])

        return list(ipv4_addresses), list(ipv6_addresses)
    except socket.gaierror as e:
        raise e
    except Exception as e:
        raise e


# --- построение строк -------------------------------------------------------


def format_record(record, settings):
    """Собирает строку маршрута в выбранном формате."""
    network = record.network
    ip = network.network_address
    prefix = network.prefixlen
    mask = network.netmask
    fmt = settings.format
    cidr = f"{ip}/{prefix}"

    if fmt == "win":
        if record.family == 6:
            return f"route -p add {cidr} interface={settings.iface}"
        template = "route -p add {ip} mask {mask} {gw}" if settings.persistent \
            else "route add {ip} mask {mask} {gw}"
        return template.format(ip=ip, mask=mask, gw=settings.gateway)

    if fmt == "keenetic-bat":
        if record.family == 6:
            return f"route -p add {cidr} interface={settings.iface}"
        return f"route add {ip} mask {mask} 0.0.0.0"

    if fmt == "unix":
        # iproute2: обязателен 'add', шлюз задаётся через 'via', интерфейс —
        # через 'dev'. Значение по умолчанию 0.0.0.0 здесь означает «не задан»
        # (в формате win это был корректный on-link шлюз).
        has_gateway = settings.gateway != "0.0.0.0"
        base = "ip -6 route add" if record.family == 6 else "ip route add"
        if has_gateway:
            return f"{base} {cidr} via {settings.gateway}"
        if settings.interface:
            return f"{base} {cidr} dev {settings.interface}"
        return f"{base} {cidr}"

    if fmt == "keenetic":
        gateway = settings.gateway
        if settings.interface:
            gateway = f"{gateway} {settings.interface}"
        tail = f" !{settings.comment}" if settings.comment else ""
        return f"ip route {cidr} {gateway} auto{tail}"

    if fmt == "mikrotik":
        comment = f' comment="{settings.comment}"' if settings.comment else ""
        return (f"/ip/firewall/address-list add list={settings.list_name}"
                f"{comment} address={cidr}")

    if fmt == "ovpn":
        return f'push "route {ip} {mask}"'

    if fmt == "wireguard" or fmt == "cidr":
        return cidr

    if fmt == "amnezia":
        return f'    {{"hostname": "{cidr}", "ip": ""}}'

    if fmt == "ip":
        return str(ip)

    raise ValueError(f"unknown format: {fmt}")


def validate_records(records, settings):
    """Строгая проверка: строка должна соответствовать формату и своей сети."""
    fmt = settings.format
    for record in records:
        line = record.line
        network = record.network
        cidr = f"{network.network_address}/{network.prefixlen}"
        stripped = line.strip()

        if not stripped:
            raise ValueError(f"empty line: {line!r}")

        if fmt == "amnezia":
            # у JSON-элемента законный отступ в 4 пробела
            if line != "    " + stripped:
                raise ValueError(f"bad indentation: {line!r}")
            if "  " in stripped:
                raise ValueError(f"double spaces: {line!r}")
        else:
            if line != stripped:
                raise ValueError(f"empty line or stray spaces: {line!r}")
            if "  " in line:
                raise ValueError(f"double spaces: {line!r}")

        if fmt in ("win", "keenetic-bat"):
            if record.family == 6:
                if not V6_LINE_RE.match(line):
                    raise ValueError(f"bad IPv6 line: {line!r}")
            elif not V4_LINE_RE.match(line):
                raise ValueError(f"bad route line: {line!r}")
            elif record.family == 4:
                gateway = settings.gateway if fmt == "win" else "0.0.0.0"
                expected = f"mask {network.netmask} {gateway}"
                if expected not in line:
                    raise ValueError(f"mask/gateway mismatch: {line!r}")
            continue

        if fmt in ("wireguard", "cidr"):
            if line != cidr:
                raise ValueError(f"expected {cidr!r}, got {line!r}")
            continue

        if fmt == "amnezia":
            if line != f'    {{"hostname": "{cidr}", "ip": ""}}':
                raise ValueError(f"bad amnezia line: {line!r}")
            continue

        if fmt == "ip":
            if line != str(network.network_address):
                raise ValueError(f"bad ip line: {line!r}")
            continue

        if fmt == "ovpn":
            if f'push "route {network.network_address} {network.netmask}"' not in line:
                raise ValueError(f"address/mask mismatch: {line!r}")
            continue

        if fmt == "mikrotik":
            if not line.startswith("/ip/firewall/address-list add ") \
                    or f"address={cidr}" not in line:
                raise ValueError(f"bad mikrotik line: {line!r}")
            continue

        if fmt == "unix":
            prefix = "ip -6 route add " if record.family == 6 \
                else "ip route add "
            if not line.startswith(prefix) or cidr not in line:
                raise ValueError(f"bad unix line: {line!r}")
            continue

        if cidr not in line:
            raise ValueError(f"address/prefix mismatch: {line!r}")
    return True


# --- вход и выход -----------------------------------------------------------


def read_targets(path):
    """Читает входной файл, выкидывая пустые строки и BOM."""
    with open(path, "r", encoding="utf-8-sig") as infile:
        return [line.strip() for line in infile if line.strip()]


def is_useless(network):
    """Маршрут в 0.0.0.0/0 или multicast сломает маршрутизацию."""
    if network.version != 4:
        return False
    if network.prefixlen == 0:
        return True
    return any(network.subnet_of(bad) for bad in USELESS_V4)


def breadth_warning(network):
    """Слишком широкий IPv4-маршрут перехватит трафик, не относящийся к делу."""
    if network.version == 4 and network.prefixlen <= 8:
        return network
    return None


def classify(line):
    """Возвращает ('v4'|'v6', сеть) для IP-литерала/CIDR либо None для домена."""
    candidate = line.strip()

    if IPV4_RE.match(candidate):
        try:
            return "v4", ipaddress.ip_network(candidate, strict=False)
        except ValueError:
            return None

    if ":" in candidate and IPV6_RE.match(candidate):
        try:
            return "v6", ipaddress.ip_network(candidate, strict=False)
        except ValueError:
            return None

    return None


def make_record(family, network, settings):
    record = RouteRecord(family, network)
    record.line = format_record(record, settings)
    return record


def lookup(host, settings):
    """Резолвит имя выбранным способом, с повторами и ограничением частоты."""
    error = None
    for attempt in range(settings.retries):
        try:
            if settings.dns_servers:
                return dnsclient.resolve(host, settings.dns_servers,
                                         settings.dns_timeout,
                                         limiter=settings.limiter)
            if settings.limiter is not None:
                settings.limiter.acquire()
            return get_all_ip_addresses(host)
        except (socket.gaierror, dnsclient.DnsError) as exc:
            error = exc
            if attempt + 1 < settings.retries:
                time.sleep(0.25 * (attempt + 1))
    raise error


def resolve_target(line, settings):
    """Обрабатывает одну строку входа. Ничего не печатает — это работа вызывающего."""
    if settings.passthrough:
        direct = classify(line)
        if direct:
            kind, network = direct
            if is_useless(network):
                return Outcome("unusable", line, network=network)
            family = 4 if kind == "v4" else 6
            record = make_record(family, network, settings)
            state = "ip" if network.prefixlen == network.max_prefixlen else "net"
            return Outcome(state, line, network=network, records=[record])

    clean_host = clean_hostname(line)
    if not clean_host:
        return Outcome("invalid", line)

    try:
        ipv4_addresses, ipv6_addresses = lookup(clean_host, settings)
    except (socket.gaierror, dnsclient.DnsError) as error:
        return Outcome("dns_error", line, host=clean_host, error=str(error))
    except Exception as error:
        return Outcome("error", line, host=clean_host, error=str(error))

    if not ipv4_addresses and not ipv6_addresses:
        return Outcome("none", line, host=clean_host)

    records = []
    for ip in ipv4_addresses:
        records.append(make_record(4, ipaddress.ip_network(f"{ip}/32"), settings))
    for ip in ipv6_addresses:
        records.append(make_record(6, ipaddress.ip_network(f"{ip}/128"), settings))

    return Outcome("domain", line, host=clean_host, ipv4=list(ipv4_addresses),
                   ipv6=list(ipv6_addresses), records=records)


def iter_outcomes(lines, settings):
    """Выдаёт результаты в порядке входного файла, при jobs > 1 — параллельно."""
    if settings.jobs <= 1 or len(lines) <= 1:
        for line in lines:
            yield resolve_target(line, settings)
        return

    with ThreadPoolExecutor(max_workers=settings.jobs) as pool:
        futures = {pool.submit(resolve_target, line, settings): index
                   for index, line in enumerate(lines)}
        pending = {}
        next_index = 0
        for future in as_completed(futures):
            pending[futures[future]] = future.result()
            while next_index in pending:
                yield pending.pop(next_index)
                next_index += 1


def finalize(records, settings):
    """Дедупликация и/или сортировка."""
    if settings.dedup:
        unique = OrderedDict()
        for record in records:
            unique.setdefault(record.line, record)
        records = list(unique.values())

    if settings.sort:
        records = sorted(records, key=lambda r: r.sort_key())

    return records


def prepare(records, settings):
    """Дедупликация → свёртка в подсети → проверка формата.

    Возвращает (записи, сколько их было после дедупликации).
    """
    records = finalize(records, settings)
    after_dedup = len(records)

    if settings.aggregate_enabled:
        records = aggregate_records(records, settings)

    if settings.strict:
        validate_records(records, settings)

    return records, after_dedup


def build_payload(records, spec):
    """Собирает содержимое файла с учётом разделителей, заголовка и подвала."""
    lines = [record.line for record in records]

    if spec.name == "wireguard":
        text = spec.separator.join(lines)
        return text + EOL if text else ""

    if spec.name == "amnezia":
        if not lines:
            return "[]" + EOL
        return spec.header + spec.separator.join(lines) + spec.footer

    return "".join(line + EOL for line in lines)


def resolve_output_path(path, spec):
    path = Path(path)
    if spec.extension:
        path = path.with_suffix(spec.extension)
    return path


def write_output(path, records, spec, settings):
    """Пишет файл (или несколько частей, если формат это требует)."""
    path = resolve_output_path(path, spec)
    # Если указали путь в несуществующую папку — создаём её сами.
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [record.line for record in records]

    if spec.chunk and settings.chunk and len(lines) > spec.chunk:
        parts = []
        for number, start in enumerate(range(0, len(lines), spec.chunk), 1):
            chunk = records[start:start + spec.chunk]
            part = path.with_name(f"{path.stem}_p{number}{path.suffix}")
            part.write_text(build_payload(chunk, spec), encoding="utf-8",
                            newline="")
            parts.append((part, len(chunk)))
        return parts

    path.write_text(build_payload(records, spec), encoding="utf-8", newline="")
    return [(path, len(records))]


# --- печать -----------------------------------------------------------------


def render(outcome, settings, v4_records, v6_records, counters):
    """Печатает сообщения по одному результату и раскладывает записи."""
    say = settings.say
    kind = outcome.kind

    if kind == "unusable":
        print(say("l_unusable", value=outcome.value))
        counters["rejected"] += 1
        return

    if kind in ("ip", "net"):
        key = "l_already_ip" if kind == "ip" else "l_already_net"
        print(say(key, value=outcome.value))
        warning = breadth_warning(outcome.network) if outcome.network else None
        if warning:
            print(say("l_wide", network=warning))
        for record in outcome.records:
            if record.family == 4:
                v4_records.append(record)
                counters["ipv4"] += 1
            else:
                v6_records.append(record)
                counters["ipv6"] += 1
        counters["passthrough"] += 1
        return

    if kind == "invalid":
        print(say("l_invalid", value=outcome.value))
        counters["rejected"] += 1
        return

    if kind == "dns_error":
        print(say("l_looking_up", host=outcome.host))
        print(say("l_resolve_failed", host=outcome.value))
        print(say("l_dns_error", error=outcome.error))
        counters["rejected"] += 1
        return

    if kind == "error":
        print(say("l_looking_up", host=outcome.host))
        print(say("l_process_error", host=outcome.value, error=outcome.error))
        counters["rejected"] += 1
        return

    if kind == "none":
        print(say("l_looking_up", host=outcome.host))
        print(say("l_no_ips", host=outcome.host))
        counters["rejected"] += 1
        return

    # домен с адресами
    print(say("l_looking_up", host=outcome.host))
    for record in outcome.records:
        if record.family == 4:
            v4_records.append(record)
            counters["ipv4"] += 1
        else:
            v6_records.append(record)
            counters["ipv6"] += 1
    counters["resolved"] += 1

    if outcome.ipv4:
        print(say("l_ipv4", host=outcome.host, list=", ".join(outcome.ipv4)))
    if outcome.ipv6:
        print(say("l_ipv6", host=outcome.host, list=", ".join(outcome.ipv6)))


def report_progress(done, total, settings, stream=sys.stderr):
    if settings.jobs <= 1 or not stream.isatty():
        return
    if done % 50 == 0 or done == total:
        stream.write(f"\r[{done}/{total}]")
        stream.flush()
        if done == total:
            stream.write("\r" + " " * 24 + "\r")
            stream.flush()


# --- основной сценарий ------------------------------------------------------


def run(settings):
    say = settings.say
    try:
        lines = read_targets(settings.input_path)
    except FileNotFoundError:
        print(say("l_input_missing", path=settings.input_path))
        return 1
    except Exception as error:
        print(say("l_fatal", error=error))
        return 1

    if not lines:
        print(say("l_empty", path=settings.input_path))
        return 0

    print(say("l_read", n=len(lines)))
    if settings.jobs_capped:
        print(say("l_jobs_capped", limit=MAX_JOBS))
    if settings.dns_servers:
        print(say("l_using_dns", servers=", ".join(
            f"{host}:{port}" for host, port in settings.dns_servers)))
    if settings.format == "unix" and settings.gateway == "0.0.0.0" \
            and not settings.interface:
        print(say("l_unix_hint"))

    v4_records = []
    v6_records = []
    counters = {"resolved": 0, "passthrough": 0, "ipv4": 0, "ipv6": 0,
                "rejected": 0}

    total = len(lines)
    for done, outcome in enumerate(iter_outcomes(lines, settings), 1):
        render(outcome, settings, v4_records, v6_records, counters)
        report_progress(done, total, settings)

    try:
        if settings.modern:
            code = finish_modern(settings, v4_records, v6_records, counters,
                                 total)
        else:
            code = finish_legacy(settings, v4_records, v6_records, counters,
                                 total)
    except ValueError as error:
        print(say("l_format_failed", error=error))
        return 2
    except Exception as error:
        print(say("l_fatal", error=error))
        return 1
    return code


def finish_legacy(settings, v4_records, v6_records, counters, total):
    say = settings.say
    v4_before = len(v4_records)

    v4_records, v4_deduped = prepare(v4_records, settings)
    v6_records, _ = prepare(v6_records, settings)

    spec = settings.spec()
    v4_parts = write_output(settings.output_path, v4_records, spec, settings)
    write_output(settings.ipv6_output_path, v6_records, spec, settings)

    print()
    print(say("l_total_legacy", ok=counters["resolved"], total=total))
    print(say("l_total_ipv4", n=counters["ipv4"]))
    print(say("l_total_ipv6", n=counters["ipv6"]))
    if v4_before != v4_deduped:
        print(say("l_dups", n=v4_before - v4_deduped))
    if v4_deduped != len(v4_records):
        print(say("l_aggregated", before=v4_deduped, after=len(v4_records)))

    print()
    for path, count in v4_parts:
        print(say("l_ipv4_file", path=path))
    if counters["ipv6"]:
        print(say("l_ipv6_file", path=settings.ipv6_output_path))
    return 0


def finish_modern(settings, v4_records, v6_records, counters, total):
    say = settings.say
    v4_before = len(v4_records)

    v4_records, v4_deduped = prepare(v4_records, settings)
    v6_records, _ = prepare(v6_records, settings)

    spec = settings.spec()
    v4_parts = write_output(settings.output_path, v4_records, spec, settings)
    if v6_records:
        write_output(settings.ipv6_output_path, v6_records, spec, settings)

    print()
    print(say("l_modern_total", domains=counters["resolved"],
              passed=counters["passthrough"], lines=total))

    dups = v4_before - v4_deduped
    suffix = say("l_dups_suffix", n=dups) if dups else ""
    print(say("l_routes_written", family="IPv4", n=len(v4_records)) + suffix)
    if v4_deduped != len(v4_records):
        print(say("l_aggregated", before=v4_deduped, after=len(v4_records)))
    print(say("l_routes_written", family="IPv6", n=len(v6_records)))
    print(say("l_format", format=settings.format,
              example=say(spec.example_key)))
    if counters["rejected"]:
        print(say("l_rejected", n=counters["rejected"]))

    print()
    for path, count in v4_parts:
        print(say("l_ipv4_file", path=path))
    if v6_records:
        print(say("l_ipv6_file", path=settings.ipv6_output_path))
    return 0


# --- командная строка -------------------------------------------------------


EXAMPLES = [
    "dns_resolver.exe",
    "dns_resolver.exe --modern",
    "dns_resolver.exe -i spisok.txt -o out.txt --modern --jobs 16",
    "dns_resolver.exe --keenetic --gateway 10.0.0.1 --interface Wireguard0 "
    "--comment telegram",
    "dns_resolver.exe --amnezia -o amnezia.json",
    "dns_resolver.exe --keenetic-bat -o keebat.bat",
]


def build_epilog(language):
    say = lambda key, **kw: i18n.translate(language, key, **kw)
    width = max(len(name) for name in FORMATS) + 3

    lines = [say("h_examples")]
    for example in EXAMPLES:
        lines.append(f"  {example}")
    lines.append("")
    lines.append(say("h_example_input"))
    lines.append("  telegram.org")
    lines.append("  1.2.3.4")
    lines.append("  91.108.4.0/22")
    lines.append("")
    lines.append(say("h_formats"))
    for name in FORMATS:
        spec = FORMAT_SPECS[name]
        lines.append(f"  --{name:<{width - 2}} {say(spec.example_key)}")
    lines.append("")
    lines.append(say("h_paths"))
    lines.append("")
    lines.append(say("h_exit_codes"))
    return "\n".join(lines)


def build_parser(language):
    say = lambda key, **kw: i18n.translate(language, key, **kw)

    parser = argparse.ArgumentParser(
        prog="dns_resolver",
        description=say("h_desc"),
        epilog=build_epilog(language),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-i", "--input", default="input.txt",
                        help=say("h_input"))
    parser.add_argument("-o", "--output", nargs="?", const=NO_VALUE,
                        default=UNSET, metavar="PATH", help=say("h_output"))
    parser.add_argument("--ipv6-output", nargs="?", const=NO_VALUE,
                        default=UNSET, metavar="PATH",
                        help=say("h_ipv6_output"))

    formats = parser.add_argument_group(say("h_group_format"))
    fmt_group = formats.add_mutually_exclusive_group()
    for name in FORMATS:
        fmt_group.add_argument(
            f"--{name}", dest="format", action="store_const", const=name,
            help=say(FORMAT_SPECS[name].example_key))

    params = parser.add_argument_group(say("h_group_params"))
    params.add_argument("--gateway", default="0.0.0.0", help=say("h_gateway"))
    params.add_argument("--interface", default="", help=say("h_interface"))
    params.add_argument("--list", default="vpn", help=say("h_list"))
    params.add_argument("--comment", default="", help=say("h_comment"))
    params.add_argument("--iface", type=int, default=0, help=say("h_iface"))
    params.add_argument("--dns", action="append", metavar="IP[:PORT]",
                        help=say("h_dns"))
    params.add_argument("--dns-timeout", type=float, default=2.0, metavar="SEC",
                        help=say("h_dns_timeout"))

    behaviour = parser.add_argument_group(say("h_group_behaviour"))
    behaviour.add_argument("--jobs", type=int, default=8, metavar="N",
                           help=say("h_jobs"))
    behaviour.add_argument("--retries", type=int, default=2, metavar="N",
                           help=say("h_retries"))
    behaviour.add_argument("--qps", type=int, default=0, metavar="N",
                           help=say("h_qps"))
    behaviour.add_argument("--aggregate-budget", type=int, default=UNSET,
                           metavar="N", help=say("h_aggregate_budget"))
    behaviour.add_argument("--aggregate-max", type=int, default=24,
                           metavar="PREFIX", help=say("h_aggregate_max"))
    behaviour.add_argument("--aggregate-max-v6", type=int, default=64,
                           metavar="PREFIX", help=say("h_aggregate_max_v6"))
    behaviour.add_argument("--sort", action="store_true", help=say("h_sort"))
    behaviour.add_argument("--passthrough", dest="passthrough",
                           action="store_true", default=True,
                           help=say("h_passthrough"))
    behaviour.add_argument("--no-passthrough", dest="passthrough",
                           action="store_false", help=say("h_no_passthrough"))
    behaviour.add_argument("--strict", action="store_true", help=say("h_strict"))
    behaviour.add_argument("--persistent", action="store_true",
                           help=say("h_persistent"))
    behaviour.add_argument("--no-chunk", action="store_true",
                           help=say("h_no_chunk"))
    behaviour.add_argument("--modern", action="store_true", help=say("h_modern"))

    language_group = parser.add_argument_group(say("h_group_lang"))
    language_group.add_argument("--lang", choices=i18n.LANGUAGES, default=None,
                                help=say("h_lang"))

    parser.add_argument("--version", action="version",
                        version=f"dns_resolver {VERSION}")
    parser.set_defaults(format=None)
    return parser


def language_from_argv(argv):
    """Достаёт --lang ещё до разбора: справка тоже должна быть на нём."""
    for index, argument in enumerate(argv):
        if argument == "--lang" and index + 1 < len(argv):
            return i18n.normalize_language(argv[index + 1])
        if argument.startswith("--lang="):
            return i18n.normalize_language(argument.split("=", 1)[1])
    return None


def make_output_forgiving():
    """Не падать, если консоль не умеет кодировать символы языка интерфейса.

    Например, на Windows с кодовой страницей 1252 кириллица в перенаправленный
    вывод не кодируется: без этого программа завершалась бы с трейсбеком.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    make_output_forgiving()
    argv = list(sys.argv[1:] if argv is None else argv)
    language = language_from_argv(argv) or i18n.detect_language()

    # Windows-привычка: /? наравне с --help
    if any(argument in ("/?", "-?", "/help") for argument in argv):
        build_parser(language).print_help()
        return 0

    args = build_parser(language).parse_args(argv)

    try:
        settings = Settings(args, language)
    except ValueError as error:
        print(i18n.translate(language, "l_bad_dns", error=error))
        return 2

    code = run(settings)

    if settings.pause:
        try:
            input(settings.say("l_press_enter"))
        except EOFError:
            pass

    return code


if __name__ == "__main__":
    sys.exit(main())
