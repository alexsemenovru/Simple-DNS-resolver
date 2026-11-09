# Simple DNS resolver
[Русский](README.md) | [English](README.en.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md)

Domains, ready-made IPs and subnets → static routes for Windows, Linux,
Keenetic, Mikrotik, OpenVPN, WireGuard and AmneziaVPN.

A single executable file, no dependencies, nothing to install. Input is a plain
text list; output is a file of `route` / `ip route` commands you can apply or
import into a router.

## Download

All files live in [Releases](../../releases).

| Platform | File | Tested on |
|---|---|---|
| Windows | `dns_resolver.exe` | Windows 10/11 x64 |
| Linux | `dns_resolver` | Ubuntu 22.04 x86_64 |

The Linux build is made on Ubuntu 22.04 (glibc 2.35): it runs there and on
newer systems; on older distributions rebuild it from source.

## How it works

One address per line in the input file — a domain, a bare IP or a subnet:

```
telegram.org
1.2.3.4
91.108.4.0/22
```

Domains are resolved; ready-made addresses are passed through without DNS. The
result is a route file:

```
route add 149.154.167.99 mask 255.255.255.255 0.0.0.0
route add 1.2.3.4 mask 255.255.255.255 0.0.0.0
route add 91.108.4.0 mask 255.255.252.0 0.0.0.0
```

IPv6 is written to a separate file: in Russia ISPs almost never provide IPv6,
and some routers (Keenetic, for example) can misbehave with such addresses.

## Quick start

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

Without flags you get a plain IPv4 route list in the format native to the
system (`win` on Windows, `unix` on Linux), with the same parsing rules.

## Output formats

Default is the system format. The format flags are mutually exclusive; the
prefix always comes from the network itself: `/32` for a single IP, `/22` for a
subnet.

| Flag | What it writes | File |
|---|---|---|
| `--win` | `route add 1.2.3.4 mask 255.255.255.255 0.0.0.0` | `output.txt` |
| `--unix` | `ip route add 1.2.3.4/32 via 10.0.0.1` | `output.txt` |
| `--keenetic` | `ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram` | `output.txt` |
| `--keenetic-bat` | the same `route add` lines, 999 per file | `output.bat`, `output_p1.bat`… |
| `--mikrotik` | `/ip/firewall/address-list add list=vpn address=1.2.3.4/32` | `output.txt` |
| `--ovpn` | `push "route 1.2.3.4 255.255.255.255"` | `output.txt` |
| `--wireguard` | `1.2.3.4/32, 5.6.7.8/32` on one line | `output.txt` |
| `--amnezia` | `[{"hostname": "1.2.3.4/32", "ip": ""}]` | `output.json` |
| `--cidr` | `1.2.3.4/32` | `output.txt` |
| `--ip` | `1.2.3.4` | `output.txt` |

Parameters: `--gateway`, `--interface` (keenetic and unix), `--list`,
`--comment`, `--iface`, `--no-chunk`.

## Custom DNS

By default queries go through the system resolver. With `--dns` they go straight
to the given server, bypassing the ISP's DNS:

```bash
./dns_resolver --dns 1.1.1.1 --modern
./dns_resolver --dns 8.8.8.8:5353 --dns 1.1.1.1 --dns-timeout 3
```

A and AAAA records, CNAME, name compression and TCP fallback on truncated
answers are supported. Servers are tried in order.

## Languages

The interface is available in English, Russian, Spanish and Chinese. The
language is detected from the system; `--lang en|ru|es|zh` overrides it.

## Flags

```
-i, --input PATH          input file                     (input.txt)
-o, --output [PATH]       IPv4 routes                    (output.txt)
    --ipv6-output [PATH]  IPv6 routes                    (output-IPv6.txt)
    --dns IP[:PORT]       custom DNS server (repeatable)
    --dns-timeout SEC     per-query timeout              (2.0)
    --jobs N              parallel lookups               (8)
    --retries N           attempts per name              (2)
    --aggregate-budget N  up to N extra addresses (0 disables)
    --aggregate-max P     no blocks larger than /P     (24)
    --sort --strict --modern
    --passthrough / --no-passthrough
    --persistent          route -p add for IPv4 in win
    --lang en|ru|es|zh
    --version
```

## Paths and Enter

`-o` takes a full path including folders; missing folders are created.

When `-o` or `--ipv6-output` is given, the program does not wait for Enter at the
end — that is the batch and scheduler mode. If you do not need to change paths
but want no wait either, pass the flag without a value:

```
dns_resolver.exe -o --modern
```

Without those flags you get "Press Enter to exit..." at the end, so a window
opened by double-click does not close immediately.

## Subnet aggregation

Adjacent addresses are merged into subnets: two in a row become `/31`, four
become `/30`. This does not widen the routing scope — coverage stays exactly the
same as in the list, so aggregation is always on. On a file with 5 827
addresses it gives 4 157 lines instead of 5 827 (−28.7 %) with no extra
addresses at all.

To shrink further, let a block take in a few addresses that were not in the
list:

```
dns_resolver.exe --aggregate-budget 2
```

`--aggregate-budget 0` disables aggregation entirely — the file gets individual
addresses. `--aggregate-max 24` (the default) forbids blocks larger than `/24`:
16 allows `/16`, and 32 effectively turns merging off.

> With a non-zero budget the routes will cover addresses that were not in the
> list: the routing scope widens. That is a deliberate trade-off for routing
> table size, worth remembering for split tunnelling.

## What it does and does not do

**Removes duplicates.** One line per IP per domain means thousands of repeats:
a list of 10 312 Telegram domains yields 19 unique routes instead of 10 311
lines. Duplicates are always collapsed and cannot be turned off; `--sort` makes
the order stable.

**Keeps the format.** UTF-8 without BOM, native line endings, exactly one space
between fields, file ends with a newline. With `--strict` every line is checked
against its format template, and a mismatch exits with code 2.

**Passes ready addresses through.** IPs and subnets are not sent to DNS:
`91.108.4.0/22` immediately becomes a route with mask `255.255.252.0`. Routes to
`0.0.0.0/0`, multicast and link-local are skipped with a message.

**Works in parallel.** 10 312 domains: 991 s one by one, 207 s with `--jobs 16`.

> **Careful with threads.** That is thousands of DNS packets within seconds. On
> a weak home router such a run ends with a reboot instead of an error message.
> Hence the default `--jobs 8`; for fragile networks use `--jobs 2` or
> `--jobs 1`.

## Building

**Windows:**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install pyinstaller
.\build.cmd
```

**Linux** — PyInstaller does not cross-compile, so build on Linux:

```bash
python3 -m pip install --user pyinstaller
python3 -m PyInstaller --noconfirm --clean --onefile --console \
    --name dns_resolver --paths src --distpath dist --workpath build --specpath build \
    src/dns_resolver.py
```

## Tests

```powershell
.venv\Scripts\python.exe tests\test_dns_resolver.py
```

```bash
python3 tests/test_dns_resolver.py
```

65 checks, no internet needed: DNS is stubbed, and for `--dns` a local UDP
server is started. In environments where UDP on loopback is not delivered, the
network tests are reported as skipped rather than failing.

## Inspiration

The project is inspired by
[DomainMapper](https://github.com/Ground-Zerro/DomainMapper/): the set of output
formats — `win`, `unix`, `keenetic`, `keenetic-bat`, `mikrotik`, `ovpn`,
`wireguard`, `amnezia`, `cidr` and `ip` — comes from there. There are two
deliberate differences: `--unix` adds `add` and `via`/`dev` (without them the
command does not add a route), and the prefix is taken from the network itself
instead of being chosen by hand.

It started as a small personal utility for turning IPs into routes. Its
reference behaviour was reconstructed from bytecode and lives in
`recovered/dns_resolver.py`; the `TestLegacyParity` test relies on it.
## License

[MIT](LICENSE)
