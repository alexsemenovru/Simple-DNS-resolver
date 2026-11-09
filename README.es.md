# Simple DNS resolver
[Русский](README.md) | [English](README.en.md) | [Español](README.es.md) | [简体中文](README.zh-CN.md)

Dominios, IP ya conocidas y subredes → rutas estáticas para Windows, Linux,
Keenetic, Mikrotik, OpenVPN, WireGuard y AmneziaVPN.

Un solo ejecutable, sin dependencias y sin instalación. La entrada es una lista
de texto; la salida es un archivo con comandos `route` / `ip route` que puedes
aplicar o importar en un router.

## Descargar

Todos los archivos están en [Releases](../../releases).

| Plataforma | Archivo | Probado en |
|---|---|---|
| Windows | `dns_resolver.exe` | Windows 10/11 x64 |
| Linux | `dns_resolver` | Ubuntu 22.04 x86_64 |

La versión de Linux está compilada en Ubuntu 22.04 (glibc 2.35): funciona ahí y
en versiones más nuevas; en distribuciones más antiguas conviene recompilarla.

## Cómo funciona

En el archivo de entrada, una dirección por línea: un dominio, una IP o una
subred.

```
telegram.org
1.2.3.4
91.108.4.0/22
```

Los dominios se resuelven y las direcciones ya conocidas se trasladan tal cual,
sin DNS. El resultado es un archivo de rutas:

```
route add 149.154.167.99 mask 255.255.255.255 0.0.0.0
route add 1.2.3.4 mask 255.255.255.255 0.0.0.0
route add 91.108.4.0 mask 255.255.252.0 0.0.0.0
```

IPv6 se escribe en un archivo aparte: en Rusia los proveedores casi nunca dan
IPv6, y algunos routers (Keenetic, por ejemplo) pueden comportarse mal con esas direcciones.

## Inicio rápido

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

Sin opciones se obtiene una lista simple de rutas IPv4 en el formato propio del
sistema (`win` en Windows, `unix` en Linux), con las mismas reglas de análisis.

## Formatos de salida

Por defecto, el formato del sistema. Las opciones de formato son mutuamente
excluyentes; el prefijo siempre se toma de la propia red: `/32` para una IP
suelta, `/22` para una subred.

| Opción | Qué escribe | Archivo |
|---|---|---|
| `--win` | `route add 1.2.3.4 mask 255.255.255.255 0.0.0.0` | `output.txt` |
| `--unix` | `ip route add 1.2.3.4/32 via 10.0.0.1` | `output.txt` |
| `--keenetic` | `ip route 1.2.3.4/32 10.0.0.1 Wireguard0 auto !telegram` | `output.txt` |
| `--keenetic-bat` | las mismas líneas `route add`, 999 por archivo | `output.bat`, `output_p1.bat`… |
| `--mikrotik` | `/ip/firewall/address-list add list=vpn address=1.2.3.4/32` | `output.txt` |
| `--ovpn` | `push "route 1.2.3.4 255.255.255.255"` | `output.txt` |
| `--wireguard` | `1.2.3.4/32, 5.6.7.8/32` en una línea | `output.txt` |
| `--amnezia` | `[{"hostname": "1.2.3.4/32", "ip": ""}]` | `output.json` |
| `--cidr` | `1.2.3.4/32` | `output.txt` |
| `--ip` | `1.2.3.4` | `output.txt` |

Parámetros: `--gateway`, `--interface` (keenetic y unix), `--list`,
`--comment`, `--iface`, `--no-chunk`.

## DNS propio

Por defecto las consultas van por el resolutor del sistema. Con `--dns` van
directamente al servidor indicado, sin pasar por el DNS del proveedor:

```bash
./dns_resolver --dns 1.1.1.1 --modern
./dns_resolver --dns 8.8.8.8:5353 --dns 1.1.1.1 --dns-timeout 3
```

Se admiten registros A y AAAA, CNAME, compresión de nombres y cambio a TCP
cuando la respuesta viene truncada. Los servidores se prueban en orden.

## Idiomas

La interfaz está en inglés, ruso, español y chino. El idioma se detecta del
sistema; `--lang en|ru|es|zh` lo cambia.

## Opciones

```
-i, --input PATH          archivo de entrada             (input.txt)
-o, --output [PATH]       rutas IPv4                     (output.txt)
    --ipv6-output [PATH]  rutas IPv6                     (output-IPv6.txt)
    --dns IP[:PORT]       servidor DNS propio (repetible)
    --dns-timeout SEC     tiempo de espera por consulta  (2.0)
    --jobs N              consultas en paralelo          (8)
    --retries N           intentos por nombre            (2)
    --sort --strict --modern
    --passthrough / --no-passthrough
    --persistent          route -p add para IPv4 en win
    --lang en|ru|es|zh
    --version
```

## Rutas y Enter

`-o` acepta una ruta completa con carpetas; si la carpeta no existe, se crea.

Si se indica `-o` o `--ipv6-output`, el programa no espera a Enter al final: es
el modo para scripts y el programador de tareas. Si no hace falta cambiar rutas
pero tampoco esperar, basta con la opción sin valor:

```
dns_resolver.exe -o --modern
```

Sin esas opciones al final aparece «Pulse Enter para salir...», para que la
ventana no se cierre al abrir el programa con doble clic.

## Qué hace y qué no hace

**Quita duplicados.** Una línea por cada IP de cada dominio son miles de
repeticiones: una lista de 10 312 dominios de Telegram produce 19 rutas únicas
en lugar de 10 311 líneas. Los duplicados se eliminan siempre y no se pueden desactivar; `--sort`
fija el orden.

**Mantiene el formato.** UTF-8 sin BOM, fin de línea propio del sistema,
exactamente un espacio entre campos, el archivo termina con salto de línea. Con
`--strict` cada línea se valida contra la plantilla de su formato y una
discrepancia devuelve el código 2.

**Traslada direcciones ya conocidas.** Las IP y subredes no van al DNS:
`91.108.4.0/22` se convierte de inmediato en una ruta con máscara
`255.255.252.0`. Las rutas a `0.0.0.0/0`, multicast y link-local se omiten con
un mensaje.

**Trabaja en paralelo.** 10 312 dominios: 991 s de uno en uno, 207 s con
`--jobs 16`.

> **Cuidado con los hilos.** Son miles de paquetes DNS en segundos. En un router
> doméstico débil esa ejecución termina en un reinicio del router, no en un
> mensaje de error. Por eso el valor por defecto es `--jobs 8`; en redes
> frágiles usa `--jobs 2` o `--jobs 1`.

## Compilación

**Windows:**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install pyinstaller
.\build.cmd
```

**Linux** — PyInstaller no compila de forma cruzada, hay que compilar en Linux:

```bash
python3 -m pip install --user pyinstaller
python3 -m PyInstaller --noconfirm --clean --onefile --console \
    --name dns_resolver --paths src --distpath dist --workpath build --specpath build \
    src/dns_resolver.py
```

## Pruebas

```powershell
.venv\Scripts\python.exe tests\test_dns_resolver.py
```

```bash
python3 tests/test_dns_resolver.py
```

65 comprobaciones, sin necesidad de internet: el DNS se sustituye por un doble y
para `--dns` se levanta un servidor UDP local. En entornos donde UDP en loopback
no se entrega, las pruebas de red se marcan como omitidas en vez de fallar.

## Inspiración

El proyecto está inspirado en
[DomainMapper](https://github.com/Ground-Zerro/DomainMapper/): de allí proviene
el conjunto de formatos de salida — `win`, `unix`, `keenetic`, `keenetic-bat`,
`mikrotik`, `ovpn`, `wireguard`, `amnezia`, `cidr` e `ip`. Hay dos diferencias
deliberadas: `--unix` añade `add` y `via`/`dev` (sin ellos el comando no añade la
ruta), y el prefijo se toma de la propia red en lugar de elegirse a mano.

Nació como una pequeña utilidad personal para convertir IP en rutas. Su
comportamiento de referencia se reconstruyó a partir del bytecode y vive en
`recovered/dns_resolver.py`; de él depende la prueba `TestLegacyParity`.
## Licencia

[MIT](LICENSE)
