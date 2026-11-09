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

IPv6 写入单独的文件：在俄罗斯运营商几乎不提供 IPv6，而某些路由器（例如 Keenetic）在这类地址上可能出问题。

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
-i, --input PATH          输入文件                    (input.txt)
-o, --output [PATH]       IPv4 路由                   (output.txt)
    --ipv6-output [PATH]  IPv6 路由                   (output-IPv6.txt)
    --dns IP[:PORT]       自定义 DNS 服务器（可重复）
    --dns-timeout SEC     单次查询超时                (2.0)
    --jobs N              并发查询数                  (8)
    --qps N               所有线程每秒查询数（0 不限）
    --retries N           每个名称的尝试次数          (2)
    --aggregate-budget N  每块最多 N 个额外地址（0 关闭）
    --aggregate-max P     不创建大于 /P 的块          (24)
    --sort --strict --modern
    --passthrough / --no-passthrough
    --persistent          win 格式下对 IPv4 使用 route -p add
    --lang en|ru|es|zh
    --version
```

## 路径与 Enter

`-o` 接受包含目录的完整路径；目录不存在时会自动创建。

指定 `-o` 或 `--ipv6-output` 后，程序在结束时不等待 Enter——这是批处理和
计划任务模式。如果不需要改路径但也不想等待，可以只写参数而不带值：

```
dns_resolver.exe -o --modern
```

不使用这些参数时，结尾会显示「按 Enter 退出...」，以免双击运行时窗口
立刻关闭。

## 合并为子网

相邻地址会合并为子网：两个相邻地址合成 `/31`，四个合成 `/30`。这不会扩大
路由范围——覆盖范围与列表完全一致，因此合并始终开启。在 5 827 个地址的文件
上，得到 4 157 行而不是 5 827 行（−28.7%），且没有多余地址。

若需要进一步压缩，可以允许每个块额外包含少量不在列表中的地址：

```
dns_resolver.exe --aggregate-budget 2
```

`--aggregate-budget 0` 完全关闭合并，文件中将是单个地址。
`--aggregate-max 24`（默认）禁止创建大于 `/24` 的块：设为 16 允许 `/16`，
设为 32 实际上关闭合并。

> 预算大于零时，路由会覆盖列表中原本没有的地址，路由范围会扩大。这是为
> 缩小路由表体积而做出的有意取舍。

## 做了什么，没做什么

**去除重复。** 每个域名的每个 IP 都写一行，会产生成千上万次重复：10 312 个
Telegram 域名只得到 19 条唯一路由，而不是 10 311 行。重复项始终合并，无法关闭；
`--sort` 让顺序稳定。

**严格保持格式。** UTF-8 无 BOM、系统原生换行、字段之间恰好一个空格、文件以
换行结尾。使用 `--strict` 时每行都会按对应格式的模板校验，不符合则返回代码 2。

**直接写入现成地址。** IP 和子网不送 DNS：`91.108.4.0/22` 立刻变成掩码为
`255.255.252.0` 的路由。指向 `0.0.0.0/0`、组播和链路本地的路由会被跳过并
给出提示。

**并行工作。** 10 312 个域名：逐个解析 991 秒，`--jobs 16` 时 207 秒。

> **注意线程数。** 这是几秒钟内发出数千个 DNS 包。在性能较弱家用路由器上，
> 这样的运行会以路由器重启结束，而不是报错。因此默认 `--jobs 8`。
> 抑制突发更有效的是 `--qps`：它限制的是速率而不只是并发——
> `--qps 5` 表示所有线程合计每秒最多五个查询。

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

## 灵感来源

本项目受 [DomainMapper](https://github.com/Ground-Zerro/DomainMapper/) 启发：
输出格式集合（`win`、`unix`、`keenetic`、`keenetic-bat`、`mikrotik`、`ovpn`、
`wireguard`、`amnezia`、`cidr`、`ip`）取自该项目。有两处刻意的不同：`--unix`
增加了 `add` 与 `via`/`dev`（否则命令不会添加路由），前缀取自网络本身，而
不是手动选择。

它最初是一个把 IP 转换成路由的小工具。其基准行为由字节码还原，保存在
`recovered/dns_resolver.py`，`TestLegacyParity` 测试依赖它。
## 许可证

[MIT](LICENSE)
