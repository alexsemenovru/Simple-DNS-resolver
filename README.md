# Easy DNS resolver
[Русский](README.md) | [English](README.en.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md)

Домены, готовые IP и подсети → статические маршруты для Windows, Linux,
Keenetic, Mikrotik, OpenVPN, WireGuard и AmneziaVPN.

Один исполняемый файл, без зависимостей и без установки. Вход — обычный
текстовый список, выход — файл с командами `route`/`ip route`, который можно
применить или импортировать в роутер.

## Скачать

Все файлы — в разделе [Releases](../../releases).

| Платформа | Файл | Проверено |
|---|---|---|
| Windows | `dns_resolver.exe` | Windows 10/11 x64 |
| Linux | `dns_resolver` | Ubuntu 22.04 x86_64 |

Linux-версия собрана на Ubuntu 22.04 (glibc 2.35): на нём и новее работает,
на более старых дистрибутивах лучше пересобрать.

## Как это работает

Во входном файле — по одному адресу в строке. Это может быть домен, готовый
IP или подсеть:

```
telegram.org
1.2.3.4
91.108.4.0/22
```

Программа резолвит домены, а готовые адреса переносит как есть, без DNS.
Результат — файл с маршрутами:

```
route add 149.154.167.99 mask 255.255.255.255 0.0.0.0
route add 1.2.3.4 mask 255.255.255.255 0.0.0.0
route add 91.108.4.0 mask 255.255.252.0 0.0.0.0
```

IPv6 пишется в отдельный файл: в РФ провайдеры почти не выдают IPv6, и Keenetic
на таких адресах может начать дурить.

## Быстрый старт

```powershell
# Windows
dns_resolver.exe
dns_resolver.exe --modern
dns_resolver.exe --dns 1.1.1.1 --modern --jobs 4
dns_resolver.exe -o "C:\Lists\Telegram.txt" --modern
dns_resolver.exe /?
```

```bash
# Linux
chmod +x dns_resolver
./dns_resolver
./dns_resolver --gateway 10.8.0.1 --modern
./dns_resolver --dns 1.1.1.1 --gateway 10.8.0.1 --modern --jobs 4
```

Без флагов — простой список маршрутов IPv4 в формате, родном для системы
(`win` на Windows, `unix` на Linux), с прежними правилами разбора.

## Форматы вывода

Без флага — формат системы. Ключи взаимоисключающие, префикс берётся из самой
сети: `/32` для одиночного IP, `/22` для подсети.

| Ключ | Что пишет | Файл |
|---|---|---|
| `--win` | `route add 1.2.3.4 mask 255.255.255.255 0.0.0.0` | `output.txt` |
| `--unix` | `ip route add 1.2.3.4/32 via 10.0.0.1` | `output.txt` |
| `--keenetic` | `ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram` | `output.txt` |
| `--keenetic-bat` | те же `route add`, по 999 строк на файл | `output.bat`, `output_p1.bat`… |
| `--mikrotik` | `/ip/firewall/address-list add list=vpn address=1.2.3.4/32` | `output.txt` |
| `--ovpn` | `push "route 1.2.3.4 255.255.255.255"` | `output.txt` |
| `--wireguard` | `1.2.3.4/32, 5.6.7.8/32` одной строкой | `output.txt` |
| `--amnezia` | `[{"hostname": "1.2.3.4/32", "ip": ""}]` | `output.json` |
| `--cidr` | `1.2.3.4/32` | `output.txt` |
| `--ip` | `1.2.3.4` | `output.txt` |

Параметры: `--gateway`, `--interface` (для keenetic и unix), `--list`,
`--comment`, `--iface`, `--no-chunk`.

## Свой DNS

Запросы идут через системный резолвер, а с ключом `--dns` — напрямую в
указанный сервер, мимо DNS провайдера:

```bash
./dns_resolver --dns 1.1.1.1 --modern
./dns_resolver --dns 8.8.8.8:5353 --dns 1.1.1.1 --dns-timeout 3
```

Поддерживаются A и AAAA, CNAME, сжатие имён и переход на TCP при усечённом
ответе. Серверы перебираются по порядку.

## Языки

Интерфейс на английском, русском, испанском и китайском. Язык определяется по
системе, ключ `--lang en|ru|es|zh` переопределяет.

## Флаги

```
-i, --input PATH        входной файл                   (input.txt)
-o, --output PATH       маршруты IPv4                  (output.txt)
    --ipv6-output PATH  маршруты IPv6                  (output-IPv6.txt)
    --dns IP[:PORT]     свой DNS-сервер (можно повторять)
    --dns-timeout SEC   таймаут запроса                (2.0)
    --jobs N            одновременных запросов         (8)
    --retries N         попыток на имя                 (2)
    --dedup --sort --strict --modern
    --passthrough / --no-passthrough
    --persistent        route -p add для IPv4 в win
    --lang en|ru|es|zh  --no-pause  --version
```

## Что делает и чего не делает

**Убирает дубли.** Строка на каждый IP каждого домена — это тысячи повторов:
у списка из 10 312 доменов Telegram получается 19 уникальных маршрутов вместо
10 311 строк. `--dedup` схлопывает повторы, `--sort` делает порядок стабильным.

**Держит формат.** UTF-8 без BOM, перевод строки родной для системы, один
пробел между полями, файл кончается переводом строки. При `--strict` каждая
строка сверяется с шаблоном своего формата, а несоответствие даёт код 2.

**Переносит готовые адреса.** IP и подсети не отправляются в DNS: `91.108.4.0/22`
сразу становится маршрутом с маской `255.255.252.0`. Маршруты в `0.0.0.0/0`,
multicast и link-local пропускаются с сообщением.

**Работает параллельно.** 10 312 доменов: 991 с по одному, 207 с при
`--jobs 16`.

> **Осторожно с потоками.** Это тысячи DNS-пакетов за секунды. На слабом
> домашнем роутере такой прогон заканчивается его перезагрузкой, а не
> сообщением об ошибке. Поэтому по умолчанию `--jobs 8`; если сеть хрупкая —
> `--jobs 2` или `--jobs 1`.

## Сборка

**Windows:**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install pyinstaller
.\build.cmd
```

**Linux** — PyInstaller не кросс-компилирует, собирать нужно на Linux:

```bash
python3 -m pip install --user pyinstaller
python3 -m PyInstaller --noconfirm --clean --onefile --console \
    --name dns_resolver --paths src --distpath dist --workpath build --specpath build \
    src/dns_resolver.py
```

## Тесты

```powershell
.venv\Scripts\python.exe tests\test_dns_resolver.py
```

```bash
python3 tests/test_dns_resolver.py
```

65 проверок, интернет не нужен: DNS подменяется заглушкой, для `--dns`
поднимается локальный UDP-сервер. В окружениях, где UDP на loopback не
доставляется, сетевые тесты помечаются пропущенными, а не падают.

## Откуда взялся исходник

Утилита выросла из небольшого приложения, чей исходник был потерян. Поведение
восстановлено по байткоду собранного exe (`recovered/dns_resolver.py` — эталон)
и закреплено тестом `TestLegacyParity`: старый и новый код запускаются на одном
входе, сравниваются лог и файлы маршрутов.

## Лицензия

[MIT](LICENSE)
