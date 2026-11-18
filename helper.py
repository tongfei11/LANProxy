#!/usr/bin/python3
"""Root-owned fixed-path service controller. Never accepts executable paths."""
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from core import REDSOCKS, atomic_write, firewall_rules, redsocks_config, resolve_lan, validate
BASE = Path(__file__).resolve().parent
STATE = Path('/var/lib/zero-proxy')
UNIT = 'zero-proxy.service'
NFT = '/usr/sbin/nft'

def run(*args, check=True, **kwargs):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=20, **kwargs)

def active():
    return run('/usr/bin/systemctl', 'is-active', '--quiet', UNIT, check=False).returncode == 0

def badge(running):
    import tempfile
    target = Path('/usr/share/APPLaunch/applications/zero-proxy.desktop')
    template = (BASE / 'zero-proxy.desktop').read_text()
    if running:
        template = template.replace('zero-proxy.png', 'zero-proxy-active.png')
    if target.exists() and target.read_text() == template:
        return
    fd, name = tempfile.mkstemp(dir=target.parent, prefix='.zero-proxy-')
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(template)
        os.chmod(name, 0o644)
        os.replace(name, target)
    finally:
        if os.path.exists(name): os.unlink(name)

def cleanup():
    marker = STATE / 'owns-redirect'
    if marker.exists():
        deletion = run(NFT, 'delete', 'table', 'inet', 'zproxy_lite', check=False)
        if deletion.returncode and run(NFT, 'list', 'table', 'inet', 'zproxy_lite', check=False).returncode == 0:
            raise ValueError('代理网络规则清理失败')
        marker.unlink()
    badge(False)

def activate():
    if run(NFT, 'list', 'table', 'inet', 'zproxy_lite', check=False).returncode == 0:
        raise ValueError('代理网络规则已存在，无法启动')
    marker = STATE / 'owns-redirect'
    marker.touch(mode=0o600)
    try:
        run(NFT, '-f', '-', input=firewall_rules())
    except subprocess.CalledProcessError:
        marker.unlink()
        raise

def verify_transparent():
    failures = []
    for url in ('https://example.com', 'https://example.org'):
        result = run('/usr/bin/curl', '--disable', '--noproxy', '*', '--ipv4',
                     '--connect-timeout', '12', '--max-time', '15', '--silent', '--fail',
                     '--output', '/dev/null', url, check=False)
        if result.returncode == 0:
            return
        failures.append(result.returncode)
    if all(code == 6 for code in failures):
        raise ValueError('代理 DNS 查询失败，请检查代理是否允许 HTTPS DNS')
    raise ValueError('代理已响应，但系统转发测试失败')


def probe(data, ip):
    auth = ''
    if data['username'] or data['password']:
        auth = quote(data['username'], safe='') + ':' + quote(data['password'], safe='') + '@'
    scheme = 'socks5h' if data['protocol'] == 'socks5' else 'http'
    url = scheme + '://' + auth + ip + ':' + str(data['port'])
    # Config on stdin keeps credentials out of process listings and logs.
    line = url.replace('\\', '\\\\').replace('"', '\\"')
    p = run('/usr/bin/curl', '--disable', '--config', '-', '--noproxy', '', '--connect-timeout', '5',
            '--max-time', '12', '--silent', '--show-error', '--fail', '--output', '/dev/null',
            '--write-out', '%{http_connect}',
            'https://example.com', input='proxy = "' + line + '"\n', check=False)
    if not p.returncode:
        return
    tunnel = p.stdout.strip()
    detail = p.stderr.lower()
    if tunnel == '407' or (data['protocol'] == 'socks5' and p.returncode in (67, 94, 97)
                           and any(word in detail for word in ('auth', 'password', 'credentials', 'user was rejected'))):
        message = '代理认证失败，请检查用户名和密码'
    elif tunnel == '403':
        message = '代理拒绝 HTTPS 转发，请检查服务端权限'
    elif tunnel.isascii() and tunnel.isdigit() and 300 <= int(tunnel) <= 599:
        message = f'代理无法建立 HTTPS 隧道（HTTP {tunnel}）'
    elif p.returncode == 7:
        message = '无法连接代理，请检查局域网、地址和端口'
    elif p.returncode == 28:
        message = '代理测试超时，请检查局域网和代理服务'
    elif p.returncode in (35, 60):
        message = 'HTTPS 验证失败，请检查设备时间和代理服务'
    elif p.returncode in (1, 8, 52, 56, 97) and tunnel != '200':
        message = '代理握手失败，请核对 HTTP / SOCKS5 和端口'
    else:
        message = '代理访问测试网站失败，请检查代理出口'
    raise ValueError(message)

def main():
    if os.geteuid() != 0: raise ValueError('需要系统权限')
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action == 'cleanup': cleanup(); return {}
    if action == 'activate': activate(); return {}
    if action == 'badge': badge(active()); return {}
    if action == 'status':
        ok = active()
        return {'active': ok, 'message': '代理运行中' if ok else '未连接'}
    if action not in ('connect', 'disconnect'): raise ValueError('无效操作')
    with open('/run/lock/zero-proxy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action == 'disconnect':
            run('/usr/bin/systemctl', 'stop', UNIT)
            cleanup()
            return {'active': False, 'message': '已断开'}
        data = validate(json.loads(sys.stdin.read(8193)))
        ip = resolve_lan(data['host'])
        probe(data, ip)
        if not Path(REDSOCKS).is_file():
            raise ValueError('缺少 redsocks，请检查应用安装')
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        candidate = STATE / 'candidate.conf'
        atomic_write(candidate, redsocks_config(data, ip))
        try:
            run(REDSOCKS, '-t', '-c', str(candidate))
            run('/usr/bin/systemctl', 'stop', UNIT)
            os.replace(candidate, STATE / 'redsocks.conf')
        finally:
            candidate.unlink(missing_ok=True)
        try:
            run('/usr/bin/systemctl', 'start', UNIT)
            verify_transparent()
            if not active():
                raise ValueError('代理服务已退出，请检查设备日志')
            badge(True)
        except Exception as error:
            run('/usr/bin/systemctl', 'stop', UNIT, check=False)
            cleanup()
            if isinstance(error, ValueError):
                raise
            raise ValueError('代理服务启动失败，请检查设备日志') from None
        return {'active': True, 'message': '代理运行中'}

if __name__ == '__main__':
    try: print(json.dumps(main(), ensure_ascii=False))
    except Exception as exc:
        # Do not leak credentials or generated configs via CalledProcessError.
        print(str(exc) if isinstance(exc, ValueError) else '系统操作失败，请检查 zero-proxy 服务日志')
        sys.exit(1)
