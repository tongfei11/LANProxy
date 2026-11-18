"""Unprivileged client for the LAN Proxy control socket."""
import json
import socket
from pathlib import Path
from core import DEFAULT, atomic_json, validate
CONFIG = Path.home() / '.config/lan-proxy/config.json'
LEGACY_CONFIG = Path.home() / '.config/zero-proxy/config.json'
LANGUAGE = CONFIG.with_name('language.json')
CONTROL_SOCKET = '/run/lan-proxy-control.sock'

def load_config():
    path = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    try: return validate(json.loads(path.read_text()))
    except (OSError, ValueError, TypeError): return dict(DEFAULT)

def save_config(data):
    atomic_json(CONFIG, validate(data))

def call(action, data=None):
    request = json.dumps({'action': action, 'config': data}, ensure_ascii=False).encode()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(65)
            connection.connect(CONTROL_SOCKET)
            connection.sendall(request + b'\n')
            with connection.makefile('rb') as reply:
                result = json.loads(reply.readline(4096))
    except TimeoutError:
        raise RuntimeError('设备操作超时，请稍后重试') from None
    except PermissionError:
        raise RuntimeError('无法控制代理服务，请检查设备权限') from None
    except (OSError, ValueError):
        raise RuntimeError('无法启动代理控制程序') from None
    if 'error' in result:
        raise RuntimeError(result['error'])
    return result

def status():
    return call('status')

def check_connection():
    return call('check')

def connect(config):
    config = validate(config)
    save_config(config)
    return call('connect', config)

def disconnect():
    return call('disconnect')

def load_language():
    try:
        return 'cn' if json.loads(LANGUAGE.read_text()) == 'cn' else 'en'
    except (OSError, ValueError):
        return 'en'

def save_language(language):
    atomic_json(LANGUAGE, language)
