"""Минимальный DNS-клиент на стандартной библиотеке.

Нужен, чтобы спрашивать конкретный сервер (--dns), чего socket.getaddrinfo
не умеет. Поддерживаются A и AAAA, сжатие имён, CNAME и переход на TCP при
усечении ответа. Никаких зависимостей.
"""

import ipaddress
import secrets
import socket
import struct

QTYPE_A = 1
QTYPE_CNAME = 5
QTYPE_AAAA = 28
CLASS_IN = 1

RCODE_NOERROR = 0
RCODE_NXDOMAIN = 3

MAX_CNAME_DEPTH = 5
MAX_COMPRESSION_JUMPS = 64


class DnsError(Exception):
    """Ответ не получен или пришёл мусор."""


def encode_name(name):
    """Домен → последовательность length-prefixed меток."""
    labels = [label for label in name.rstrip(".").split(".") if label]
    payload = b""
    for label in labels:
        try:
            raw = label.encode("idna")
        except UnicodeError:
            raw = label.encode("ascii", "replace")
        if not 0 < len(raw) < 64:
            raise DnsError(f"bad label: {label!r}")
        payload += bytes([len(raw)]) + raw
    return payload + b"\x00"


def build_query(name, qtype, query_id):
    header = struct.pack("!HHHHHH", query_id, 0x0100, 1, 0, 0, 0)
    return header + encode_name(name) + struct.pack("!HH", qtype, CLASS_IN)


def read_name(data, offset):
    """Читает имя, разворачивая указатели сжатия. Возвращает (имя, новый offset)."""
    labels = []
    end = None
    jumps = 0

    while True:
        if offset >= len(data):
            raise DnsError("truncated name")
        length = data[offset]

        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(data):
                raise DnsError("truncated pointer")
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if end is None:
                end = offset + 2
            offset = pointer
            jumps += 1
            if jumps > MAX_COMPRESSION_JUMPS:
                raise DnsError("compression loop")
            continue

        offset += 1
        if length == 0:
            return ".".join(labels), (end if end is not None else offset)

        if offset + length > len(data):
            raise DnsError("truncated label")
        labels.append(data[offset:offset + length].decode("latin-1"))
        offset += length


def parse_response(data, query_id, expect_name=None, expect_qtype=None):
    """Разбирает ответ. Возвращает (rcode, truncated, адреса, cname-цели)."""
    if len(data) < 12:
        raise DnsError("short response")

    rid, flags, qdcount, ancount, _, _ = struct.unpack("!HHHHHH", data[:12])
    if rid != query_id:
        raise DnsError("query id mismatch")

    truncated = bool(flags & 0x0200)
    rcode = flags & 0x000F

    offset = 12
    for index in range(qdcount):
        question_name, offset = read_name(data, offset)
        if offset + 4 > len(data):
            raise DnsError("truncated question")
        question_type, _ = struct.unpack("!HH", data[offset:offset + 4])
        offset += 4

        # Ответ должен относиться к тому, о чём спрашивали: иначе сервер (или
        # тот, кто подсунул пакет) может подменить данные при верном ID.
        if index == 0 and expect_name is not None:
            same_name = (question_name.rstrip(".").lower()
                         == expect_name.rstrip(".").lower())
            if not same_name or question_type != expect_qtype:
                raise DnsError("response does not match the question")

    addresses = []
    cnames = []

    for _ in range(ancount):
        _, offset = read_name(data, offset)
        if offset + 10 > len(data):
            raise DnsError("truncated answer")

        rtype, rclass, _, rdlength = struct.unpack("!HHIH", data[offset:offset + 10])
        offset += 10
        rdata = data[offset:offset + rdlength]
        if len(rdata) != rdlength:
            raise DnsError("bad rdata length")

        if rclass == CLASS_IN:
            if rtype == QTYPE_A and rdlength == 4:
                addresses.append(str(ipaddress.IPv4Address(rdata)))
            elif rtype == QTYPE_AAAA and rdlength == 16:
                addresses.append(str(ipaddress.IPv6Address(rdata)))
            elif rtype == QTYPE_CNAME:
                target, _ = read_name(data, offset)
                cnames.append(target)

        offset += rdlength

    return rcode, truncated, addresses, cnames


def send_udp(server, port, packet, timeout):
    """UDP-запрос на соединённом сокете: ядро само отсекает чужие ответы."""
    with socket.socket(socket.AF_INET6 if ":" in server else socket.AF_INET,
                       socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((server, port))
        sock.send(packet)
        return sock.recv(4096)


def send_tcp(server, port, packet, timeout):
    with socket.create_connection((server, port), timeout=timeout) as sock:
        sock.sendall(struct.pack("!H", len(packet)) + packet)
        head = sock.recv(2)
        if len(head) < 2:
            raise DnsError("tcp: short length prefix")
        (length,) = struct.unpack("!H", head)
        chunks = []
        received = 0
        while received < length:
            chunk = sock.recv(length - received)
            if not chunk:
                break
            chunks.append(chunk)
            received += len(chunk)
    return b"".join(chunks)


def query_once(server, port, name, qtype, timeout, force_tcp=False):
    """Один запрос. При усечении ответа повторяет его по TCP."""
    query_id = secrets.randbits(16)
    packet = build_query(name, qtype, query_id)

    data = (send_tcp(server, port, packet, timeout) if force_tcp
            else send_udp(server, port, packet, timeout))
    rcode, truncated, addresses, cnames = parse_response(
        data, query_id, expect_name=name, expect_qtype=qtype)

    if truncated and not force_tcp:
        return query_once(server, port, name, qtype, timeout, force_tcp=True)

    return rcode, addresses, cnames


def resolve(name, servers, timeout=2.0, depth=0, limiter=None):
    """Спрашивает серверы по очереди. Возвращает (список IPv4, список IPv6)."""
    if depth > MAX_CNAME_DEPTH:
        raise DnsError("CNAME chain too long")

    last_error = None

    for server, port in servers:
        addresses_v4 = set()
        addresses_v6 = set()
        answered = False

        for qtype, bucket in ((QTYPE_A, addresses_v4), (QTYPE_AAAA, addresses_v6)):
            try:
                if limiter is not None:
                    limiter.acquire()
                rcode, addresses, cnames = query_once(server, port, name, qtype,
                                                      timeout)
            except (OSError, DnsError) as error:
                last_error = error
                continue

            if rcode == RCODE_NXDOMAIN:
                return [], []
            if rcode != RCODE_NOERROR:
                # SERVFAIL и прочие отказы — это ошибка, а не «адресов нет»
                last_error = DnsError(f"{server} returned rcode {rcode}")
                continue

            answered = True

            for address in addresses:
                bucket.add(address)

            # сервер может отдать только CNAME — идём по цепочке
            for target in cnames:
                try:
                    nested_v4, nested_v6 = resolve(target, [(server, port)],
                                                   timeout, depth + 1,
                                                   limiter=limiter)
                except (OSError, DnsError) as error:
                    last_error = error
                    # если ничего не нашли, честнее сообщить ошибку, чем
                    # «адресов нет»: цепочка CNAME оборвалась
                    if not addresses_v4 and not addresses_v6:
                        answered = False
                    continue
                addresses_v4.update(nested_v4)
                addresses_v6.update(nested_v6)

        if answered:
            return sorted(addresses_v4, key=_ip_key), sorted(addresses_v6,
                                                              key=_ip_key)

    raise DnsError(f"no answer from {servers}: {last_error}")


def _ip_key(value):
    return ipaddress.ip_address(value)


def parse_servers(raw_values):
    """'1.1.1.1,8.8.8.8:5353' → [('1.1.1.1', 53), ('8.8.8.8', 5353)]."""
    servers = []
    for raw in raw_values or []:
        for chunk in str(raw).replace(";", ",").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            port = 53
            host = chunk
            if chunk.startswith("[") and "]:" in chunk:
                host, port_text = chunk[1:].split("]:", 1)
                port = int(port_text)
            elif chunk.count(":") == 1:
                host, port_text = chunk.split(":", 1)
                port = int(port_text)
            ipaddress.ip_address(host)  # проверка формата
            servers.append((host, port))
    return servers
