#!/usr/bin/python3
"""Socket-activated non-root controller for the LAN Proxy service."""
import socket
import signal
import select
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
from core import REDSOCKS, atomic_write, firewall_rules, redsocks_config, resolve_lan, validate
STATE = Path('/run/lan-proxy')
NFT = '/usr/sbin/nft'
CONTROL_TIMEOUT = 3
MAX_REQUEST = 16384

def run(*args, check=True, **kwargs):
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=20, **kwargs)

def cleanup():
    (STATE / 'forwarding').unlink(missing_ok=True)
    marker = STATE / 'owns-redirect'
    if marker.exists():
        deletion = run(NFT, 'delete', 'table', 'inet', 'zproxy_lite', check=False)
        if deletion.returncode and run(NFT, 'list', 'table', 'inet', 'zproxy_lite', check=False).returncode == 0:
            raise ValueError('代理网络规则清理失败')
        marker.unlink()

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

def verify_transparent(connect_timeout=12, max_time=15):
    failures = []
    for url in ('https://example.com', 'https://example.org'):
        result = run('/usr/bin/curl', '--disable', '--noproxy', '*', '--ipv4',
                     '--connect-timeout', str(connect_timeout), '--max-time', str(max_time), '--silent', '--fail',
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

class Controller:
    def __init__(self):
        self.relay = None

    def disconnect(self):
        try:
            cleanup()
        finally:
            if self.relay is not None:
                try:
                    os.killpg(self.relay.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.relay.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    os.killpg(self.relay.pid, signal.SIGKILL)
                    self.relay.wait()
                self.relay = None
            (STATE / 'redsocks.conf').unlink(missing_ok=True)

    def is_active(self):
        if self.relay is None:
            return False
        if self.relay.poll() is not None:
            self.disconnect()
            return False
        return True

    def connect(self, data):
        if self.is_active():
            raise ValueError('请先断开，再修改配置')
        data = validate(data)
        ip = resolve_lan(data['host'])
        probe(data, ip)
        if not Path(REDSOCKS).is_file():
            raise ValueError('缺少 redsocks，请检查应用安装')
        config = STATE / 'redsocks.conf'
        atomic_write(config, redsocks_config(data, ip))
        try:
            run(REDSOCKS, '-t', '-c', str(config))
            self.relay = subprocess.Popen(
                [sys.executable, str(Path(__file__).with_name('relay.py')), str(config)],
                stdout=subprocess.PIPE, start_new_session=True)
            self.wait_for_relay()
            activate()
            verify_transparent()
            if not self.is_active():
                raise ValueError('代理服务已退出，请检查设备日志')
            (STATE / 'forwarding').touch(mode=0o600)
        except Exception:
            self.disconnect()
            raise

    def wait_for_relay(self):
        with self.relay.stdout as ready:
            if select.select([ready], [], [], 6)[0] and ready.readline() == b'READY\n':
                return
        raise ValueError('代理服务启动失败，请检查设备日志')

    def check_connection(self):
        if not self.is_active():
            return {'active': False}
        try:
            if run(NFT, 'list', 'table', 'inet', 'zproxy_lite', check=False).returncode:
                raise ValueError('代理转发规则未生效')
            verify_transparent(connect_timeout=4, max_time=5)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            detail = str(error) if isinstance(error, ValueError) else '无法完成代理连通性检查'
            return {'active': self.is_active(), 'reachable': False, 'detail': detail}
        active = self.is_active()
        return {'active': active, 'reachable': active}

    def request(self, request):
        if not isinstance(request, dict):
            raise ValueError('无效操作')
        action = request.get('action')
        if action == 'connect':
            self.connect(request.get('config'))
        elif action == 'disconnect':
            self.disconnect()
        elif action == 'check':
            return self.check_connection()
        elif action != 'status':
            raise ValueError('无效操作')
        return {'active': self.is_active()}


def dispatch(controller, connection):
    connection.settimeout(CONTROL_TIMEOUT)
    try:
        with connection.makefile('rb') as stream:
            payload = stream.readline(MAX_REQUEST + 1)
        if len(payload) > MAX_REQUEST or not payload.endswith(b'\n'):
            return
        try:
            response = controller.request(json.loads(payload))
        except ValueError as error:
            response = {'error': str(error)}
        except (OSError, subprocess.SubprocessError):
            response = {'error': '系统操作失败，请检查 lan-proxy 服务日志'}
        connection.sendall(json.dumps(response).encode() + b'\n')
    except OSError:
        # A client can leave the interface while the requested action runs.
        pass


def main():
    if sys.argv[1:] == ['cleanup']:
        cleanup()
        return
    if os.environ.get('LISTEN_PID') != str(os.getpid()) or os.environ.get('LISTEN_FDS') != '1':
        raise RuntimeError('Start through lan-proxy.socket')
    controller = Controller()
    with socket.socket(fileno=3) as listener:
        listener.settimeout(1)
        try:
            while True:
                controller.is_active()
                try:
                    connection, _ = listener.accept()
                except socket.timeout:
                    continue
                with connection:
                    dispatch(controller, connection)
        finally:
            controller.disconnect()


if __name__ == '__main__':
    main()
