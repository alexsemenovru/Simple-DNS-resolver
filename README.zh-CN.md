# Simple DNS resolver

[Русский](README.md) | [English](README.en.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md)

把域名、现成 IP 和子网转换成 Windows、Linux、Keenetic、Mikrotik、OpenVPN、
WireGuard 和 AmneziaVPN 的静态路由。

单个可执行文件，无依赖，无需安装。输入是一个纯文本列表，输出是一个可以
直接执行或导入路由器的 `route` / `ip route` 命令文件。

## 下载

全部文件见 [Releases](../../releases)。

| 平台 | 文件 | 测试环境 |
|---|---|---|
| Windows | `dns_resolver.exe` | Windows 10/11 x64 |
| Linux | `dns_resolver` | Ubuntu 22.04 x86_64 |

Linux 版本在 Ubuntu 22.04（glibc 2.35）上编译：在该版本及更新系统上可用，
更旧的发行版建议自行重新编译。

## 工作原理

输入文件每行一个地址，可以是域名、裸 IP 或子网：

```
telegram.org
1.2.3.4
91.108.4.0/22
```

域名会被解析，现成的地址原样写入，不经过 DNS。结果是一个路由文件：

```
route add 149.154.167.99 mask 255.255.255.255 0.0.0.0
route add 1.2.3.4 mask 255.255.255.255 0.0.0.0
route add 91.108.4.0 mask 255.255.252.0 0.0.0.0
```

IPv6 写入单独的文件：在俄罗斯运营商几乎不提供 IPv6，而 Keenetic 设备在
这类地址上可能出问题。

## 快速开始

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

不带参数时输出系统原生格式的 IPv4 路由列表（Windows 为 `win`，Linux 为
`unix`），解析规则保持不变。

## 输出格式

默认使用系统格式。格式参数互斥；前缀始终取自网络本身：单 IP 为 `/32`，
子网为 `/22`。

| 参数 | 写入内容 | 文件 |
|---|---|---|
| `--win` | `route add 1.2.3.4 mask 255.255.255.255 0.0.0.0` | `output.txt` |
| `--unix` | `ip route add 1.2.3.4/32 via 10.0.0.1` | `output.txt` |
| `--keenetic` | `ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram` | `output.txt` |
| `--keenetic-bat` | 同样的 `route add` 行，每个文件 999 行 | `output.bat`、`output_p1.bat`… |
| `--mikrotik` | `/ip/firewall/address-list add list=vpn address=1.2.3.4/32` | `output.txt` |
| `--ovpn` | `push "route 1.2.3.4 255.255.255.255"` | `output.txt` |
| `--wireguard` | `1.2.3.4/32, 5.6.7.8/32` 单行 | `output.txt` |
| `--amnezia` | `[{"hostname": "1.2.3.4/32", "ip": ""}]` | `output.json` |
| `--cidr` | `1.2.3.4/32` | `output.txt` |
| `--ip` | `1.2.3.4` | `output.txt` |

其他参数：`--gateway`、`--interface`（keenetic 与 unix）、`--list`、
`--comment`、`--iface`、`--no-chunk`。

## 指定 DNS

默认通过系统解析器查询。加上 `--dns` 后直接向指定服务器查询，绕过运营商 DNS：

```bash
./dns_resolver --dns 1.1.1.1 --modern
./dns_resolver --dns 8.8.8.8:5353 --dns 1.1.1.1 --dns-timeout 3
```

支持 A 与 AAAA 记录、CNAME、名称压缩，以及响应被截断时切换到 TCP。
多个服务器按顺序尝试。

## 语言

界面支持英语、俄语、西班牙语和中文。语言由系统决定，`--lang en|ru|es|zh`
可以覆盖。

## 参数

```
-i, --input PATH        输入文件                    (input.txt)
-o, --output PATH       IPv4 路由                   (output.txt)
    --ipv6-output PATH  IPv6 路由                   (output-IPv6.txt)
    --dns IP[:PORT]     自定义 DNS 服务器（可重复）
    --dns-timeout SEC   单次查询超时                (2.0)
    --jobs N            并发查询数                  (8)
    --retries N         每个名称的尝试次数          (2)
    --dedup --sort --strict --modern
    --passthrough / --no-passthrough
    --persistent        win 格式下对 IPv4 使用 route -p add
    --lang en|ru|es|zh  --no-pause  --version
```

## 做了什么，没做什么

**去除重复。** 每个域名的每个 IP 都写一行，会产生成千上万次重复：10 312 个
Telegram 域名只得到 19 条唯一路由，而不是 10 311 行。`--dedup` 合并重复项，
`--sort` 让顺序稳定。

**严格保持格式。** UTF-8 无 BOM、系统原生换行、字段之间恰好一个空格、文件以
换行结尾。使用 `--strict` 时每行都会按对应格式的模板校验，不符合则返回代码 2。

**直接写入现成地址。** IP 和子网不送 DNS：`91.108.4.0/22` 立刻变成掩码为
`255.255.252.0` 的路由。指向 `0.0.0.0/0`、组播和链路本地的路由会被跳过并
给出提示。

**并行工作。** 10 312 个域名：逐个解析 991 秒，`--jobs 16` 时 207 秒。

> **注意线程数。** 这是几秒钟内发出数千个 DNS 包。在性能较弱家用路由器上，
> 这样的运行会以路由器重启结束，而不是报错。因此默认 `--jobs 8`；网络脆弱时
> 请用 `--jobs 2` 或 `--jobs 1`。

## 编译

**Windows：**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install pyinstaller
.\build.cmd
```

**Linux** — PyInstaller 不支持交叉编译，需要在 Linux 上编译：

```bash
python3 -m pip install --user pyinstaller
python3 -m PyInstaller --noconfirm --clean --onefile --console \
    --name dns_resolver --paths src --distpath dist --workpath build --specpath build \
    src/dns_resolver.py
```

## 测试

```powershell
.venv\Scripts\python.exe tests\test_dns_resolver.py
```

```bash
python3 tests/test_dns_resolver.py
```

65 项检查，无需联网：DNS 用桩替换，`--dns` 时启动本地 UDP 服务器。在无法
投递 loopback UDP 的环境中，网络相关测试标记为跳过而不是失败。

## 源码的来历

这个工具源自一个小程序，其源码曾经丢失。程序行为由已编译 exe 的字节码还原
（`recovered/dns_resolver.py` 为基准），并由 `TestLegacyParity` 测试固定：
新旧代码在同一输入上运行，比较日志和路由文件。

## 许可证

[MIT](LICENSE)
