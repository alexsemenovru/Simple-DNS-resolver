"""Локализация dns_resolver: определение языка системы и каталог сообщений.

Поддерживаются английский, русский, испанский и упрощённый китайский.
Фарси не подключён: консоль Windows не умеет двунаправленный текст, и вывод
получался бы с перепутанным порядком букв независимо от кода.

Порядок выбора языка:
  1. переменная DNS_RESOLVER_LANG (нужна для тестов и скриптов);
  2. язык интерфейса Windows (GetUserDefaultUILanguage);
  3. LANG / LC_ALL / LC_MESSAGES;
  4. английский.
"""

import ctypes
import os

LANGUAGES = ("en", "ru", "es", "zh")

LANGUAGE_NAMES = {
    "en": "English",
    "ru": "Русский",
    "es": "Español",
    "zh": "简体中文",
}

# Основной идентификатор языка из LANGID (младшие 10 бит).
_PRIMARY_LANG = {
    0x09: "en",
    0x19: "ru",
    0x0A: "es",
    0x04: "zh",
}


def _windows_language():
    """Язык интерфейса Windows, даже если консольная кодировка другая."""
    if os.name != "nt":
        return None
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return None
    return _PRIMARY_LANG.get(langid & 0x3FF)


def _environment_language():
    for variable in ("LANG", "LC_ALL", "LC_MESSAGES"):
        value = os.environ.get(variable, "").strip()
        if not value:
            continue
        code = value.split(".")[0].split("_")[0].split("-")[0].lower()
        if code in LANGUAGES:
            return code
    return None


def detect_language():
    """Определяет язык вывода."""
    forced = os.environ.get("DNS_RESOLVER_LANG", "").strip().lower()
    if forced in LANGUAGES:
        return forced
    return _windows_language() or _environment_language() or "en"


def normalize_language(code):
    """Приводит 'ru-RU', 'zh_CN', 'RU' к коду каталога."""
    if not code:
        return None
    code = str(code).strip().lower().replace("_", "-").split(".")[0]
    primary = code.split("-")[0]
    return primary if primary in LANGUAGES else None


# --- каталог сообщений ------------------------------------------------------
# Ключи сгруппированы по смыслу: l_* — строки лога, h_* — справка.

CATALOG = {
    # ---- лог ------------------------------------------------------------
    "l_read": {
        "en": "Read {n} targets from file",
        "ru": "Прочитано {n} адресов из файла",
        "es": "Leídos {n} destinos del archivo",
        "zh": "已从文件读取 {n} 个目标",
    },
    "l_empty": {
        "en": "File {path} is empty or contains only blank lines",
        "ru": "Файл {path} пуст или содержит только пустые строки",
        "es": "El archivo {path} está vacío o solo tiene líneas en blanco",
        "zh": "文件 {path} 为空或只含空行",
    },
    "l_looking_up": {
        "en": "Looking up IP for domain: {host}",
        "ru": "Ищу IP домена: {host}",
        "es": "Busco la IP del dominio: {host}",
        "zh": "正在查找域名 IP：{host}",
    },
    "l_already_ip": {
        "en": "Already an IP — passing through: {value}",
        "ru": "Это уже IP — переношу: {value}",
        "es": "Ya es una IP — la traslado: {value}",
        "zh": "已是 IP — 直接写入：{value}",
    },
    "l_already_net": {
        "en": "Already a subnet — passing through: {value}",
        "ru": "Это уже подсеть — переношу: {value}",
        "es": "Ya es una subred — la traslado: {value}",
        "zh": "已是子网 — 直接写入：{value}",
    },
    "l_invalid": {
        "en": "Invalid address format: {value}",
        "ru": "Некорректный формат адреса: {value}",
        "es": "Formato de dirección no válido: {value}",
        "zh": "地址格式无效：{value}",
    },
    "l_ipv4": {
        "en": "IPv4 addresses for {host}: {list}",
        "ru": "IPv4 адреса для {host}: {list}",
        "es": "Direcciones IPv4 para {host}: {list}",
        "zh": "{host} 的 IPv4 地址：{list}",
    },
    "l_ipv6": {
        "en": "IPv6 addresses for {host}: {list}",
        "ru": "IPv6 адреса для {host}: {list}",
        "es": "Direcciones IPv6 para {host}: {list}",
        "zh": "{host} 的 IPv6 地址：{list}",
    },
    "l_no_ips": {
        "en": "No IP addresses found for {host}",
        "ru": "Для {host} не найдено IP адресов",
        "es": "No se encontraron direcciones IP para {host}",
        "zh": "未找到 {host} 的 IP 地址",
    },
    "l_resolve_failed": {
        "en": "Failed to resolve host name: {host}",
        "ru": "Не удалось разрешить имя хоста: {host}",
        "es": "No se pudo resolver el nombre de host: {host}",
        "zh": "无法解析主机名：{host}",
    },
    "l_dns_error": {
        "en": "DNS error: {error}",
        "ru": "Ошибка DNS: {error}",
        "es": "Error de DNS: {error}",
        "zh": "DNS 错误：{error}",
    },
    "l_process_error": {
        "en": "Error while processing {host}: {error}",
        "ru": "Ошибка при обработке {host}: {error}",
        "es": "Error al procesar {host}: {error}",
        "zh": "处理 {host} 时出错：{error}",
    },
    "l_unusable": {
        "en": "Skipped address unusable for a route: {value}",
        "ru": "Пропущен непригодный для маршрута адрес: {value}",
        "es": "Dirección no apta para una ruta, omitida: {value}",
        "zh": "已跳过不适合路由的地址：{value}",
    },
    "l_wide": {
        "en": "Route too broad: {network} — it would capture unrelated traffic",
        "ru": "Слишком широкий маршрут: {network} — перехватит чужой трафик",
        "es": "Ruta demasiado amplia: {network} — capturaría tráfico ajeno",
        "zh": "路由范围过大：{network} — 会劫持无关流量",
    },
    # ---- итоги (legacy) --------------------------------------------------
    "l_total_legacy": {
        "en": "Total: {ok} of {total} targets resolved successfully",
        "ru": "Итого: успешно разрешено {ok} из {total} адресов",
        "es": "Total: {ok} de {total} destinos resueltos",
        "zh": "总计：成功解析 {ok}/{total} 个目标",
    },
    "l_total_ipv4": {
        "en": "Unique IPv4 addresses found: {n}",
        "ru": "Всего найдено уникальных IPv4 адресов: {n}",
        "es": "Direcciones IPv4 únicas encontradas: {n}",
        "zh": "找到的唯一 IPv4 地址数：{n}",
    },
    "l_total_ipv6": {
        "en": "Unique IPv6 addresses found: {n}",
        "ru": "Всего найдено уникальных IPv6 адресов: {n}",
        "es": "Direcciones IPv6 únicas encontradas: {n}",
        "zh": "找到的唯一 IPv6 地址数：{n}",
    },
    # ---- итоги (modern) --------------------------------------------------
    "l_modern_total": {
        "en": "Total: {domains} domains resolved, {passed} IP/CIDR passed "
              "through out of {lines} lines",
        "ru": "Итого: разрешено доменов {domains}, перенесено IP/CIDR {passed} "
              "из {lines} строк",
        "es": "Total: {domains} dominios resueltos, {passed} IP/CIDR "
              "trasladadas de {lines} líneas",
        "zh": "总计：解析域名 {domains} 个，直接写入 IP/CIDR {passed} 个"
              "（共 {lines} 行）",
    },
    "l_routes_written": {
        "en": "{family} routes written: {n}",
        "ru": "{family} маршрутов записано: {n}",
        "es": "Rutas {family} escritas: {n}",
        "zh": "已写入 {family} 路由：{n}",
    },
    "l_dups_suffix": {
        "en": " ({n} duplicates removed)",
        "ru": " (убрано дублей: {n})",
        "es": " ({n} duplicados eliminados)",
        "zh": "（已删除 {n} 个重复项）",
    },
    "l_dups": {
        "en": "Duplicates removed: {n}",
        "ru": "Повторов убрано: {n}",
        "es": "Duplicados eliminados: {n}",
        "zh": "已删除重复项：{n}",
    },
    "l_format": {
        "en": "Format: {format} — {example}",
        "ru": "Формат: {format} — {example}",
        "es": "Formato: {format} — {example}",
        "zh": "格式：{format} — {example}",
    },
    "l_rejected": {
        "en": "Rejected lines: {n}",
        "ru": "Отклонено строк: {n}",
        "es": "Líneas rechazadas: {n}",
        "zh": "已拒绝的行数：{n}",
    },
    "l_ipv4_file": {
        "en": "IPv4 routes written to file: {path}",
        "ru": "IPv4 маршруты записаны в файл: {path}",
        "es": "Rutas IPv4 escritas en el archivo: {path}",
        "zh": "IPv4 路由已写入文件：{path}",
    },
    "l_ipv6_file": {
        "en": "IPv6 routes written to file: {path}",
        "ru": "IPv6 маршруты записаны в файл: {path}",
        "es": "Rutas IPv6 escritas en el archivo: {path}",
        "zh": "IPv6 路由已写入文件：{path}",
    },
    "l_files_written": {
        "en": "Written: {files}",
        "ru": "Записано файлов: {files}",
        "es": "Archivos escritos: {files}",
        "zh": "已写入文件：{files}",
    },
    # ---- ошибки ----------------------------------------------------------
    "l_input_missing": {
        "en": "File not found: {path}",
        "ru": "Файл {path} не найден",
        "es": "No se encontró el archivo: {path}",
        "zh": "找不到文件：{path}",
    },
    "l_fatal": {
        "en": "Error: {error}",
        "ru": "Произошла ошибка: {error}",
        "es": "Error: {error}",
        "zh": "错误：{error}",
    },
    "l_format_failed": {
        "en": "Format check failed: {error}",
        "ru": "Проверка формата не пройдена: {error}",
        "es": "Error de validación de formato: {error}",
        "zh": "格式校验失败：{error}",
    },
    "l_press_enter": {
        "en": "Press Enter to exit...",
        "ru": "Нажмите Enter для завершения...",
        "es": "Pulse Enter para salir...",
        "zh": "按 Enter 退出...",
    },
    "l_using_dns": {
        "en": "DNS servers: {servers}",
        "ru": "DNS-серверы: {servers}",
        "es": "Servidores DNS: {servers}",
        "zh": "DNS 服务器：{servers}",
    },
    "l_bad_dns": {
        "en": "Invalid DNS server: {error}",
        "ru": "Некорректный DNS-сервер: {error}",
        "es": "Servidor DNS no válido: {error}",
        "zh": "DNS 服务器无效：{error}",
    },
    "l_unix_hint": {
        "en": "Hint: set --gateway or --interface, otherwise 'ip route add' "
              "has no next hop",
        "ru": "Подсказка: укажите --gateway или --interface, иначе у "
              "'ip route add' не будет шлюза",
        "es": "Sugerencia: indique --gateway o --interface, si no 'ip route "
              "add' se queda sin puerta de enlace",
        "zh": "提示：请指定 --gateway 或 --interface，否则 'ip route add' 没有下一跳",
    },
    # ---- справка ---------------------------------------------------------
    "h_desc": {
        "en": "Resolve domains and turn IP addresses into routes. Without "
              "flags: a plain IPv4 route list in the win format.",
        "ru": "Резолвит домены и раскладывает IP в маршруты. Без флагов — "
              "простой список маршрутов IPv4 в формате win.",
        "es": "Resuelve dominios y convierte direcciones IP en rutas. Sin "
              "opciones: una lista simple de rutas IPv4 en formato win.",
        "zh": "解析域名并将 IP 转换为路由。不带参数时输出 win 格式的 IPv4 路由列表。",
    },
    "h_group_output": {
        "en": "output", "ru": "вывод", "es": "salida", "zh": "输出",
    },
    "h_group_format": {
        "en": "output format (default: --win)",
        "ru": "формат вывода (по умолчанию --win)",
        "es": "formato de salida (por defecto --win)",
        "zh": "输出格式（默认 --win）",
    },
    "h_group_params": {
        "en": "format parameters", "ru": "параметры форматов",
        "es": "parámetros de formato", "zh": "格式参数",
    },
    "h_group_behaviour": {
        "en": "behaviour", "ru": "поведение", "es": "comportamiento",
        "zh": "行为",
    },
    "h_group_lang": {
        "en": "language", "ru": "язык", "es": "idioma", "zh": "语言",
    },
    "h_input": {
        "en": "input file", "ru": "входной файл",
        "es": "archivo de entrada", "zh": "输入文件",
    },
    "h_output": {
        "en": "IPv4 routes file", "ru": "файл маршрутов IPv4",
        "es": "archivo de rutas IPv4", "zh": "IPv4 路由文件",
    },
    "h_ipv6_output": {
        "en": "IPv6 routes file", "ru": "файл маршрутов IPv6",
        "es": "archivo de rutas IPv6", "zh": "IPv6 路由文件",
    },
    "h_gateway": {
        "en": "gateway for win/unix/keenetic",
        "ru": "шлюз для win/unix/keenetic",
        "es": "puerta de enlace para win/unix/keenetic",
        "zh": "win/unix/keenetic 的网关",
    },
    "h_interface": {
        "en": "interface name for keenetic",
        "ru": "имя интерфейса для keenetic",
        "es": "nombre de interfaz para keenetic",
        "zh": "keenetic 的接口名称",
    },
    "h_list": {
        "en": "address list name for mikrotik",
        "ru": "имя списка для mikrotik",
        "es": "nombre de lista para mikrotik",
        "zh": "mikrotik 的地址列表名称",
    },
    "h_comment": {
        "en": "comment for keenetic/mikrotik",
        "ru": "комментарий для keenetic/mikrotik",
        "es": "comentario para keenetic/mikrotik",
        "zh": "keenetic/mikrotik 的注释",
    },
    "h_iface": {
        "en": "interface index for IPv6 in win format",
        "ru": "индекс интерфейса для IPv6 в формате win",
        "es": "índice de interfaz para IPv6 en formato win",
        "zh": "win 格式下 IPv6 的接口索引",
    },
    "h_jobs": {
        "en": "parallel lookups (1 = one at a time); 8 is safe, 32+ may "
              "overload a home router",
        "ru": "одновременных запросов (1 = по одному); 8 безопасно, 32+ может "
              "уронить домашний роутер",
        "es": "consultas en paralelo (1 = de una en una); 8 es seguro, 32+ "
              "puede saturar un router doméstico",
        "zh": "并发查询数（1 = 逐个查询）；8 较安全，32 以上可能压垮家用路由器",
    },
    "h_retries": {
        "en": "attempts per name on DNS failure",
        "ru": "попыток на имя при сбое DNS",
        "es": "intentos por nombre si falla el DNS",
        "zh": "DNS 失败时每个名称的尝试次数",
    },
    "h_dns": {
        "en": "ask this DNS server instead of the system one; repeat the flag "
              "or use commas: --dns 1.1.1.1 --dns 8.8.8.8:53",
        "ru": "спрашивать этот DNS-сервер вместо системного; флаг можно "
              "повторять или перечислять через запятую: --dns 1.1.1.1",
        "es": "consultar este servidor DNS en lugar del del sistema; repita "
              "la opción o use comas: --dns 1.1.1.1",
        "zh": "改用指定 DNS 服务器而非系统服务器；可重复该参数或用逗号分隔："
              "--dns 1.1.1.1",
    },
    "h_dns_timeout": {
        "en": "per-query timeout in seconds",
        "ru": "таймаут одного запроса, секунды",
        "es": "tiempo de espera por consulta, en segundos",
        "zh": "单次查询超时（秒）",
    },
    "h_dedup": {
        "en": "collapse duplicate routes",
        "ru": "схлопнуть повторяющиеся маршруты",
        "es": "eliminar rutas duplicadas",
        "zh": "合并重复路由",
    },
    "h_sort": {
        "en": "stable order (by address and prefix)",
        "ru": "стабильный порядок (по адресу и префиксу)",
        "es": "orden estable (por dirección y prefijo)",
        "zh": "稳定排序（按地址和前缀）",
    },
    "h_passthrough": {
        "en": "pass IP and CIDR through without DNS (default)",
        "ru": "переносить IP и CIDR без DNS (по умолчанию)",
        "es": "trasladar IP y CIDR sin DNS (por defecto)",
        "zh": "IP 和 CIDR 不经 DNS 直接写入（默认）",
    },
    "h_no_passthrough": {
        "en": "resolve IP addresses through DNS too, as the old exe did",
        "ru": "гонять IP-адреса через DNS, как старый exe",
        "es": "resolver también las IP mediante DNS, como el exe antiguo",
        "zh": "像旧 exe 一样把 IP 也交给 DNS",
    },
    "h_strict": {
        "en": "check every line against the canonical format",
        "ru": "проверять каждую строку по каноническому формату",
        "es": "verificar cada línea contra el formato canónico",
        "zh": "按规范格式校验每一行",
    },
    "h_persistent": {
        "en": "use 'route -p add' for IPv4 in win format",
        "ru": "писать 'route -p add' для IPv4 в формате win",
        "es": "usar 'route -p add' para IPv4 en formato win",
        "zh": "win 格式下对 IPv4 使用 'route -p add'",
    },
    "h_no_chunk": {
        "en": "do not split keenetic-bat into 999-line parts",
        "ru": "не резать keenetic-bat на части по 999 строк",
        "es": "no dividir keenetic-bat en partes de 999 líneas",
        "zh": "不把 keenetic-bat 拆成 999 行的分片",
    },
    "h_modern": {
        "en": "preset: --dedup --sort --strict",
        "ru": "пресет: --dedup --sort --strict",
        "es": "preajuste: --dedup --sort --strict",
        "zh": "预设：--dedup --sort --strict",
    },
    "h_no_pause": {
        "en": "do not wait for Enter",
        "ru": "не ждать Enter",
        "es": "no esperar a Enter",
        "zh": "不等待 Enter",
    },
    "h_lang": {
        "en": "output language (default: system language)",
        "ru": "язык вывода (по умолчанию — язык системы)",
        "es": "idioma de salida (por defecto: el del sistema)",
        "zh": "输出语言（默认：系统语言）",
    },
    "h_version": {
        "en": "show version and exit", "ru": "показать версию и выйти",
        "es": "mostrar la versión y salir", "zh": "显示版本并退出",
    },
    "h_examples": {
        "en": "examples:", "ru": "примеры:", "es": "ejemplos:",
        "zh": "示例：",
    },
    "h_formats": {
        "en": "formats:", "ru": "форматы:", "es": "formatos:",
        "zh": "格式：",
    },
    "h_exit_codes": {
        "en": "exit codes: 0 — success, 1 — error, 2 — format check failed",
        "ru": "коды возврата: 0 — успех, 1 — ошибка, 2 — проверка формата не пройдена",
        "es": "códigos de salida: 0 — éxito, 1 — error, 2 — fallo de validación",
        "zh": "退出码：0 — 成功，1 — 错误，2 — 格式校验失败",
    },
    "h_example_input": {
        "en": "a file may contain domains, bare IPs and subnets:",
        "ru": "в файле могут быть домены, голые IP и подсети:",
        "es": "el archivo puede contener dominios, IP y subredes:",
        "zh": "文件中可以包含域名、裸 IP 和子网：",
    },
    # ---- описания форматов ----------------------------------------------
    "f_win": {
        "en": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0",
        "ru": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0",
        "es": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0",
        "zh": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0",
    },
    "f_unix": {
        "en": "ip route add 1.2.3.4/32 via 10.0.0.1",
        "ru": "ip route add 1.2.3.4/32 via 10.0.0.1",
        "es": "ip route add 1.2.3.4/32 via 10.0.0.1",
        "zh": "ip route add 1.2.3.4/32 via 10.0.0.1",
    },
    "f_keenetic": {
        "en": "ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram",
        "ru": "ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram",
        "es": "ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram",
        "zh": "ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram",
    },
    "f_keenetic_bat": {
        "en": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0, "
              "999 lines per file, .bat",
        "ru": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0, "
              "по 999 строк в файле, .bat",
        "es": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0, "
              "999 líneas por archivo, .bat",
        "zh": "route add 1.2.3.4 mask 255.255.255.255 0.0.0.0，每文件 999 行，.bat",
    },
    "f_mikrotik": {
        "en": '/ip/firewall/address-list add list=vpn comment="telegram" '
              "address=1.2.3.4/32",
        "ru": '/ip/firewall/address-list add list=vpn comment="telegram" '
              "address=1.2.3.4/32",
        "es": '/ip/firewall/address-list add list=vpn comment="telegram" '
              "address=1.2.3.4/32",
        "zh": '/ip/firewall/address-list add list=vpn comment="telegram" '
              "address=1.2.3.4/32",
    },
    "f_ovpn": {
        "en": 'push "route 1.2.3.4 255.255.255.255"',
        "ru": 'push "route 1.2.3.4 255.255.255.255"',
        "es": 'push "route 1.2.3.4 255.255.255.255"',
        "zh": 'push "route 1.2.3.4 255.255.255.255"',
    },
    "f_wireguard": {
        "en": "1.2.3.4/32, 5.6.7.8/32 — one line, for AllowedIPs",
        "ru": "1.2.3.4/32, 5.6.7.8/32 — одной строкой, для AllowedIPs",
        "es": "1.2.3.4/32, 5.6.7.8/32 — en una línea, para AllowedIPs",
        "zh": "1.2.3.4/32, 5.6.7.8/32 — 单行，用于 AllowedIPs",
    },
    "f_amnezia": {
        "en": '{"hostname": "1.2.3.4/32", "ip": ""} in a JSON array, .json',
        "ru": '{"hostname": "1.2.3.4/32", "ip": ""} в массиве JSON, .json',
        "es": '{"hostname": "1.2.3.4/32", "ip": ""} en un array JSON, .json',
        "zh": '{"hostname": "1.2.3.4/32", "ip": ""} 置于 JSON 数组，.json',
    },
    "f_cidr": {
        "en": "1.2.3.4/32", "ru": "1.2.3.4/32", "es": "1.2.3.4/32",
        "zh": "1.2.3.4/32",
    },
    "f_ip": {
        "en": "1.2.3.4 — address only, no prefix",
        "ru": "1.2.3.4 — только адрес, без префикса",
        "es": "1.2.3.4 — solo la dirección, sin prefijo",
        "zh": "1.2.3.4 — 仅地址，不带前缀",
    },
}


def translate(language, key, **values):
    """Возвращает сообщение на нужном языке; при отсутствии перевода — английский."""
    entry = CATALOG.get(key)
    if not entry:
        return key
    text = entry.get(language) or entry.get("en") or key
    try:
        return text.format(**values)
    except (KeyError, IndexError):
        return text
