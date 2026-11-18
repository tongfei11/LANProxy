"""Unprivileged UI API; privileged commands only accept validated JSON."""
import json
import subprocess
from pathlib import Path
from core import DEFAULT, atomic_json, validate
CONFIG = Path.home() / '.config/lan-proxy/config.json'
LEGACY_CONFIG = Path.home() / '.config/zero-proxy/config.json'
LANGUAGE = CONFIG.with_name('language.json')
HELPER = str(Path(__file__).resolve().with_name('helper.py'))

def load_config():
    path = CONFIG if CONFIG.exists() else LEGACY_CONFIG
    try: return validate(json.loads(path.read_text()))
    except (OSError, ValueError, TypeError): return dict(DEFAULT)

def save_config(data):
    atomic_json(CONFIG, validate(data))

def call(action, data=None):
    try:
        p = subprocess.run(['sudo', '-n', '/usr/bin/python3', HELPER, action],
                       input=json.dumps(data) if data is not None else '',
                       text=True, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError('设备操作超时，请稍后重试') from None
    except OSError:
        raise RuntimeError('无法启动代理控制程序') from None
    if p.returncode:
        raise RuntimeError(p.stdout.strip() or '无法控制代理服务，请检查设备权限')
    return json.loads(p.stdout)

def status():
    return call('status')

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
