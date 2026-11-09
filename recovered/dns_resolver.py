"""Восстановленный исходник dns_resolver.exe (PyInstaller, Python 3.13).

Собран из байткода: поведение воспроизведено 1:1, включая особенности.
Запуск: положить рядом input.txt со списком доменов (по одному в строке).
Результат: output.txt (IPv4) и output-IPv6.txt (IPv6).
"""

import socket
import sys
from urllib.parse import urlparse
import re


def clean_hostname(url):
    """Достаёт имя хоста из строки, которая может быть URL. Возвращает None, если формат не тот."""
    try:
        # Поддерживаем и «example.com», и «https://example.com/path»
        if '//' in url:
            parsed = urlparse(url if '://' in url else f'http://{url}')
            hostname = parsed.netloc
        else:
            hostname = url

        # Отбрасываем порт, если он указан
        hostname = hostname.split(':')[0]

        # Убираем пробелы по краям
        hostname = hostname.strip()

        # Разрешены только латиница, цифры, точка и дефис.
        # Именно поэтому строки вида 91.108.4.0/22 отбраковываются.
        if re.match(r'^[a-zA-Z0-9.-]+$', hostname):
            return hostname
        return None
    except Exception:
        return None


def get_all_ip_addresses(hostname):
    """Резолвит имя через системный резолвер, возвращает (список IPv4, список IPv6)."""
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


def resolve_and_write_routes():
    try:
        with open('input.txt', 'r', encoding='utf-8') as infile:
            hostnames = [line.strip() for line in infile if line.strip()]

        if not hostnames:
            print('Файл input.txt пуст или содержит только пустые строки')
            return

        print(f'Прочитано {len(hostnames)} адресов из файла')

        resolved_count = 0
        total_ipv4 = 0
        total_ipv6 = 0

        # Файлы открываются один раз, ещё до цикла: даже при нулевом результате
        # они будут созданы (пустыми).
        with open('output.txt', 'w', encoding='utf-8') as outfile_v4:
            with open('output-IPv6.txt', 'w', encoding='utf-8') as outfile_v6:
                for hostname in hostnames:
                    try:
                        clean_host = clean_hostname(hostname)
                        if not clean_host:
                            print(f'Некорректный формат адреса: {hostname}')
                            continue

                        print(f'Попытка разрешить адрес: {clean_host}')

                        ipv4_addresses, ipv6_addresses = get_all_ip_addresses(clean_host)

                        if ipv4_addresses or ipv6_addresses:
                            # По строке на каждый IP; дубликаты между доменами не схлопываются
                            for ip in ipv4_addresses:
                                route_command = f'route add {ip} mask 255.255.255.255 0.0.0.0'
                                outfile_v4.write(route_command + '\n')
                                total_ipv4 += 1

                            for ip in ipv6_addresses:
                                route_command = f'route -p add {ip}/128 interface=0'
                                outfile_v6.write(route_command + '\n')
                                total_ipv6 += 1

                            resolved_count += 1

                            if ipv4_addresses:
                                print(f'IPv4 адреса для {clean_host}: {", ".join(ipv4_addresses)}')
                            if ipv6_addresses:
                                print(f'IPv6 адреса для {clean_host}: {", ".join(ipv6_addresses)}')
                        else:
                            print(f'Для {clean_host} не найдено IP адресов')
                    except socket.gaierror as e:
                        print(f'Не удалось разрешить имя хоста: {hostname}')
                        print(f'Ошибка DNS: {str(e)}')
                    except Exception as e:
                        print(f'Ошибка при обработке {hostname}: {str(e)}')

        print(f'\nИтого: успешно разрешено {resolved_count} из {len(hostnames)} адресов')
        print(f'Всего найдено уникальных IPv4 адресов: {total_ipv4}')
        print(f'Всего найдено уникальных IPv6 адресов: {total_ipv6}')

        print('\nIPv4 маршруты записаны в файл: output.txt')
        if total_ipv6 > 0:
            print('IPv6 маршруты записаны в файл: output-IPv6.txt')

    except FileNotFoundError:
        print('Файл input.txt не найден')
    except Exception as e:
        print(f'Произошла ошибка: {str(e)}')


if __name__ == '__main__':
    resolve_and_write_routes()
    input('\nНажмите Enter для завершения...')
