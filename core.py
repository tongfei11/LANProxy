"""Validated single LAN proxy and generated sing-box configuration."""
import ipaddress
import json
import os
import socket
import tempfile
from pathlib import Path

DEFAULT = dict(protocol='http', host='', port=2080, username='', password='')
PRIVATE = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '127.0.0.0/8',
           '169.254.0.0/16', '100.64.0.0/10', '224.0.0.0/4', '::1/128', 'fc00::/7', 'fe80::/10', 'ff00::/8']

def validate(data):
    if not isinstance(data, dict):
        raise ValueError('配置格式错误')
    result = {key: data.get(key, value) for key, value in DEFAULT.items()}
    if result['protocol'] not in ('http', 'socks5'):
        raise ValueError('请选择 HTTP 或 SOCKS5')
    host = result['host']
    if host == '':
        raise ValueError('请先填写代理地址')
    if not isinstance(host, str) or len(host) > 253 or any(c.isspace() for c in host) or any(c in host for c in '/:@'):
        raise ValueError('请填写局域网代理地址，不含协议或端口')
    try:
        if isinstance(result['port'], bool): raise ValueError()
        result['port'] = int(result['port'])
        if not 1 <= result['port'] <= 65535: raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('端口须为 1–65535') from None
    for key in ('username', 'password'):
        if not isinstance(result[key], str) or len(result[key].encode()) > 255 or any(ord(c) < 32 for c in result[key]):
            raise ValueError('账号或密码格式错误')
    return result

def resolve_lan(host):
    try:
        addresses = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError('无法解析代理地址，请检查域名或改填局域网 IP') from None
    allowed = [ipaddress.ip_network(x) for x in PRIVATE[:3]]
    ips = [r[4][0] for r in addresses]
    if not ips or any(not any(ipaddress.ip_address(ip) in n for n in allowed) for ip in ips):
        raise ValueError('代理地址必须位于局域网 IPv4 网段')
    return ips[0]

def atomic_write(path, contents):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(contents)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def atomic_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False))

REDSOCKS = '/usr/sbin/redsocks'
TCP_PORT = 42145
DNS_PORT = 42153
DNS_MARK = 0x5a505844

def redsocks_config(data, ip):
    data = validate(data)
    proxy_type = 'http-connect' if data['protocol'] == 'http' else 'socks5'
    parts = [
        'base { log = stderr; daemon = off; redirector = iptables; }',
        'redsocks {',
        f' local_ip = 127.0.0.1; local_port = {TCP_PORT}; splice = false;',
        f' ip = {ipaddress.IPv4Address(ip)}; port = {data["port"]}; type = {proxy_type};',
    ]
    if data['username'] or data['password']:
        for option, key in (('login', 'username'), ('password', 'password')):
            parts.append(f' {option} = {json.dumps(data[key], ensure_ascii=False)};')
    return '\n'.join([*parts, '}', ''])

def firewall_rules():
    private4 = ', '.join(x for x in PRIVATE if ':' not in x)
    private6 = ', '.join(x for x in PRIVATE if ':' in x)
    return f"""add table inet zproxy_lite
add chain inet zproxy_lite nat_out {{ type nat hook output priority -101; policy accept; }}
add rule inet zproxy_lite nat_out meta mark != {DNS_MARK:#x} meta l4proto {{ tcp, udp }} th dport 53 redirect to :{DNS_PORT}
add rule inet zproxy_lite nat_out fib daddr type {{ local, broadcast, multicast }} return
add rule inet zproxy_lite nat_out ip daddr != {{ {private4} }} meta l4proto tcp redirect to :{TCP_PORT}
add chain inet zproxy_lite filter_out {{ type filter hook output priority -90; policy accept; }}
add rule inet zproxy_lite filter_out fib daddr type {{ local, broadcast, multicast }} return
add rule inet zproxy_lite filter_out ip daddr != {{ {private4} }} meta l4proto udp reject
add rule inet zproxy_lite filter_out ip6 daddr != {{ {private6} }} meta l4proto {{ tcp, udp }} reject
"""
