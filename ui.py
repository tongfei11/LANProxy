#!/usr/bin/env python3
"""Native 320 × 170 proxy controls. Closing the UI preserves the connection."""
import argparse
import importlib
import queue
import selectors
import signal
import struct
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from i18n import translate

SIZE = (320, 170)
EVENT = struct.Struct('@llHHi')
KEYBOARD = '/dev/input/by-path/platform-3f804000.i2c-event'
BG, PANEL, TEXT, DIM, GREEN = '#10151d', '#1b2531', '#edf2f8', '#adbccb', '#6ce1be'
FIELDS = [('protocol', '协议'), ('host', '代理地址'), ('port', '端口'),
          ('username', '用户名（可选）'), ('password', '密码（可选）')]
PRINTABLE = {57: (' ', ' ')}
for base, plain, shifted in (
    (2, '1234567890-=', '!@#$%^&*()_+'),
    (16, 'qwertyuiop[]', 'QWERTYUIOP{}'),
    (30, "asdfghjkl;'`", 'ASDFGHJKL:\"~'),
    (43, '\\zxcvbnm,./', '|ZXCVBNM<>?'),
):
    PRINTABLE.update({base+i: pair for i, pair in enumerate(zip(plain, shifted))})
SYMBOLS = {26: '!', 27: '@', 39: '#', 40: '$', 41: '%', 43: '^',
           51: '&', 52: '*', 53: '(', 94: ')', 55: '~', 69: '`', 70: '_',
           71: '-', 72: '+', 73: '=', 74: '[', 75: ']', 76: '{', 77: '}',
           79: ';', 80: ':', 81: "'", 82: '"', 83: '<', 85: '>',
           86: '\\', 89: '|', 90: ',', 91: '.', 92: '/', 93: '?'}


def font(size):
    for path in ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                 '/System/Library/Fonts/PingFang.ttc',
                 '/System/Library/Fonts/Hiragino Sans GB.ttc', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def fit(f, value, width, tail=False):
    value = str(value)
    if f.getlength(value) <= width:
        return value
    while value and f.getlength('…'+value if tail else value+'…') > width:
        value = value[1:] if tail else value[:-1]
    return '…'+value if tail else value+'…'


def rgb565(image):
    data = bytearray(320*170*2)
    for i, (r, g, b) in enumerate(image.convert('RGB').getdata()):
        struct.pack_into('<H', data, i*2, ((r & 248) << 8) | ((g & 252) << 3) | (b >> 3))
    return data


class App:
    def __init__(self, backend, language=None):
        self.backend = backend
        self.language = language or backend.load_language()
        self.error_prefix = None
        self.config = dict(backend.load_config())
        self.state = {'active': None, 'message': '读取状态…'}
        self.edit = None
        self.index = 0
        self.typing = False
        self.pressed = set()
        self.busy = False
        self.message = ''
        self.connection_changed = False
        self.jobs = queue.Queue()
        self.results = queue.Queue()
        self.small, self.large = font(12), font(17)
        threading.Thread(target=self.worker, daemon=True).start()
        self.submit('status')

    def worker(self):
        while True:
            name, data = self.jobs.get()
            try:
                if name == 'connect':
                    self.backend.connect(data)
                elif name == 'disconnect':
                    self.backend.disconnect()
                elif name == 'save':
                    self.backend.save_config(data)
                    self.results.put((name, data, None, None))
                    continue
                state = self.backend.status() if name == 'status' else {
                    'active': name == 'connect',
                }
                self.results.put((name, data, state, None))
            except Exception as error:
                # The client exposes safe validation/helper messages for these errors.
                if isinstance(error, (ValueError, RuntimeError)):
                    message = str(error)
                elif name == 'save':
                    message = '无法写入配置，请检查存储空间或权限'
                else:
                    message = '无法读取或控制代理服务'
                self.results.put((name, data, None, message))

    def submit(self, name, data=None):
        if self.busy:
            return
        self.busy = True
        self.jobs.put((name, data))

    def drain(self):
        changed = False
        while True:
            try:
                name, data, state, error = self.results.get_nowait()
            except queue.Empty:
                return changed
            self.busy = False
            changed = True
            if error:
                prefix = {'connect': '连接失败', 'disconnect': '断开失败',
                          'save': '保存失败', 'status': '状态读取失败'}[name]
                self.error_prefix = prefix
                self.message = error
            else:
                if state is not None:
                    self.state = state
                if name != 'status':
                    self.error_prefix = None
                if name == 'save':
                    self.config = data
                    self.edit = None
                    self.message = '配置已保存'
                elif name != 'status':
                    self.connection_changed = True
                    self.message = ''

    def tr(self, message):
        return translate(message, self.language)

    def exit_toast(self):
        if self.state['active']:
            return self.tr('代理继续在后台运行')
        if self.connection_changed and self.state['active'] is False:
            return self.tr('代理已断开')
        return ''

    def key(self, code, value):
        if value == 0:
            self.pressed.discard(code)
            return True
        self.pressed.add(code)
        if value not in (1, 2):
            return True
        if code == 38 and value == 1 and not self.typing:
            language = 'cn' if self.language == 'en' else 'en'
            try:
                self.backend.save_language(language)
            except OSError:
                self.error_prefix = None
                self.message = '无法保存语言设置'
            else:
                self.language = language
            return True
        if code == 1:
            if value != 1:
                return True
            if self.edit is None:
                return False
            if not self.busy:
                self.typing = False
                self.error_prefix = None
                self.message = '正在保存…'
                self.submit('save', dict(self.edit))
            return True
        if self.busy:
            return True
        enter = code in (28, 96) and value == 1
        if self.edit is None:
            if code == 18 and value == 1:
                self.error_prefix = None
                if self.state.get('active'):
                    self.message = '请先断开，再修改配置'
                elif self.state.get('active') is False:
                    self.edit = {k: str(self.config.get(k, '')) for k, _ in FIELDS}
                    self.index = 0
                    self.typing = False
                    self.message = ''
            elif enter and self.state.get('active') is not None:
                active = self.state['active']
                self.error_prefix = None
                self.message = '正在断开…' if active else '正在连接…'
                self.submit('disconnect' if active else 'connect', dict(self.config))
            return True

        field = FIELDS[self.index][0]
        if not self.typing:
            if code in (33, 103, 45, 108):
                step = -1 if code in (33, 103) else 1
                self.index = (self.index + step) % len(FIELDS)
            elif field == 'protocol' and (enter or (value == 1 and code in (44, 46, 105, 106))):
                self.edit[field] = 'http' if self.edit[field] == 'socks5' else 'socks5'
            elif enter and field != 'protocol':
                self.typing = True
            return True
        if enter:
            self.typing = False
            return True
        if code == 14:
            self.edit[field] = self.edit[field][:-1]
        else:
            char = SYMBOLS.get(code)
            if char is None and code in PRINTABLE:
                char = PRINTABLE[code][int(bool(self.pressed & {42, 54}))]
            if char and not self.pressed & {29, 97}:
                limit = 5 if field == 'port' else 253 if field == 'host' else 256
                if len(self.edit[field]) < limit and (field != 'port' or char.isdigit()):
                    self.edit[field] += char
        return True

    def draw(self, toast=''):
        image = Image.new('RGB', SIZE, BG)
        d = ImageDraw.Draw(image)
        d.rectangle((0, 0, 319, 29), fill=PANEL)
        d.text((9, 5), self.tr('局域网代理'), font=self.large, fill=TEXT)
        d.text((311, 9), 'EN(L)' if self.language == 'en' else 'CN(L)', font=self.small, fill=DIM, anchor='ra')
        if self.edit is not None:
            first = max(0, min(self.index-1, len(FIELDS)-3))
            for row, (field, label) in enumerate(FIELDS[first:first+3], first):
                y = 34 + (row-first)*30
                d.rounded_rectangle((6, y, 313, y+27), radius=4, fill=PANEL,
                                    outline=GREEN if row == self.index else PANEL)
                d.text((12, y+5), self.tr(label), font=self.small, fill=DIM)
                value = self.edit[field]
                if field == 'password':
                    value = '•'*len(value)
                if field == 'protocol':
                    value = value.upper() + '   ‹  ›'
                if row == self.index and self.typing:
                    value += '▏'
                d.text((308, y+5), fit(self.small, value or self.tr('未设置'), 170, True),
                       font=self.small, fill=TEXT, anchor='ra')
            if self.typing:
                footer = 'Enter 完成输入   Esc 保存返回'
            elif self.index == 0:
                footer = 'F/X 上下   左右/Enter 切换   Esc 返回'
            else:
                footer = 'F/X 上下   Enter 编辑   Esc 保存返回'
        else:
            active = self.state.get('active', False)
            d.ellipse((10, 41, 18, 49), fill=GREEN if active else DIM)
            d.text((25, 36), self.tr('代理运行中' if active else '读取状态…' if active is None else '未连接'), font=self.large,
                   fill=GREEN if active else TEXT)
            target = f"{self.config.get('protocol', 'socks5').upper()}  {self.config.get('host') or self.tr('请先编辑配置')}"
            if self.config.get('host'):
                target += ':'+str(self.config.get('port', ''))
            d.text((10, 68), fit(self.small, target, 300), font=self.small, fill=DIM)
            d.rounded_rectangle((9, 92, 310, 119), radius=5, fill=PANEL, outline=GREEN)
            label = '处理中…' if self.busy else 'Enter 断开连接' if active else 'Enter 连接代理'
            d.text((160, 96), self.tr(label), font=self.large, fill=GREEN, anchor='ma')
            footer = 'Esc 返回（保持连接）' if active else 'E 编辑配置    Esc 返回'
        message = self.tr(self.message)
        if self.error_prefix and message:
            joiner = ': ' if self.language == 'en' else '：'
            message = self.tr(self.error_prefix) + joiner + message
        if message:
            split = len(message)
            while self.small.getlength(message[:split]) > 302:
                split -= 1
            top = 121 if split < len(message) else 130
            d.text((9, top), message[:split], font=self.small, fill=DIM)
            if split < len(message):
                d.text((9, 135), fit(self.small, message[split:], 302), font=self.small, fill=DIM)
        d.rectangle((0, 150, 319, 169), fill=PANEL)
        d.text((8, 152), self.tr(footer), font=self.small, fill=DIM)
        if toast:
            width = round(self.large.getlength(toast)) + 34
            left = (SIZE[0] - width) // 2
            d.rounded_rectangle((left, 61, left + width, 108), radius=8,
                                fill=PANEL, outline=GREEN, width=2)
            d.text((160, 70), toast, font=self.large, fill=TEXT, anchor='ma')
        return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framebuffer', default='/dev/fb_lcd')
    parser.add_argument('--keyboard', default=KEYBOARD)
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--lang', choices=('en', 'cn'), help='Language for preview output')
    args = parser.parse_args()
    if args.preview:
        class Demo:
            def load_config(self):
                return dict(protocol='socks5', host='192.168.1.2', port=1080, username='', password='')
            def status(self):
                return dict(active=False, message='退出界面后，连接继续保留')
        app = App(Demo(), language=args.lang or 'en')
        app.drain()
        app.state = Demo().status()
        app.busy = False
        app.draw().save(args.preview)
        return
    backend = importlib.import_module('client')
    app = App(backend)
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with open(args.framebuffer, 'wb', buffering=0) as fb, open(args.keyboard, 'rb', buffering=0) as kb, selectors.DefaultSelector() as poll:
        poll.register(kb, selectors.EVENT_READ)
        dirty, next_status, buffer = True, time.monotonic()+2, b''
        while running:
            dirty |= app.drain()
            if time.monotonic() >= next_status:
                if not app.busy and app.edit is None:
                    app.submit('status')
                next_status = time.monotonic()+2
            if dirty:
                fb.seek(0)
                fb.write(rgb565(app.draw()))
                dirty = False
            if not poll.select(0.15):
                continue
            chunk = kb.read(EVENT.size*32)
            if not chunk:
                break
            buffer += chunk
            whole = len(buffer)//EVENT.size*EVENT.size
            for _, _, kind, code, value in EVENT.iter_unpack(buffer[:whole]):
                if kind == 1:
                    running = app.key(code, value)
                    dirty = True
                    if not running:
                        toast = app.exit_toast()
                        if toast:
                            fb.seek(0)
                            fb.write(rgb565(app.draw(toast)))
                            time.sleep(0.8)
                        break
            buffer = buffer[whole:]


if __name__ == '__main__':
    main()
