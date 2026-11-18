import time
import unittest

from ui import App, EVENT, rgb565


class Backend:
    def __init__(self):
        self.config = dict(protocol='socks5', host='192.168.1.2', port=1080, username='', password='')
        self.active = False
        self.error = False
        self.reachable = True
        self.health_checks = 0
        self.language = 'en'

    def load_language(self):
        return self.language

    def save_language(self, language):
        self.language = language

    def load_config(self):
        return self.config

    def status(self):
        return dict(active=self.active, message='Ready')

    def check_connection(self):
        self.health_checks += 1
        if self.active:
            return {'active': True, 'reachable': self.reachable, 'detail': 'Test failure'}
        return {'active': False}

    def save_config(self, config):
        if self.error:
            raise ValueError('请输入代理地址')
        self.config = config

    def connect(self, config):
        self.active = True

    def disconnect(self):
        self.active = False


def settle(app):
    deadline = time.monotonic()+2
    while app.busy and time.monotonic() < deadline:
        app.drain()
        time.sleep(0.001)
    assert not app.busy


def key(app, code):
    result = app.key(code, 1)
    app.key(code, 0)
    return result


class Controls(unittest.TestCase):
    def setUp(self):
        self.backend = Backend()
        self.app = App(self.backend)
        settle(self.app)

    def test_connect_exit_preserves_connection(self):
        key(self.app, 28)
        settle(self.app)
        self.assertTrue(self.backend.active)
        self.assertFalse(key(self.app, 1))
        self.assertEqual(self.app.exit_toast(), 'Proxy stays active')
        self.assertTrue(self.backend.active)
        key(self.app, 28)
        settle(self.app)
        self.assertFalse(self.backend.active)
        self.assertEqual(self.app.exit_toast(), 'Proxy disconnected')

    def test_language_toggle_is_persistent_and_l_stays_a_letter_in_fields(self):
        self.assertEqual(self.app.language, 'en')
        self.assertEqual(self.app.tr('未连接'), 'Disconnected')
        key(self.app, 38)
        self.assertEqual(self.app.language, 'cn')
        reopened = App(self.backend)
        settle(reopened)
        self.assertEqual(reopened.language, 'cn')
        key(reopened, 18)
        key(reopened, 45)
        key(reopened, 28)
        key(reopened, 38)
        self.assertTrue(reopened.edit['host'].endswith('l'))
        self.assertEqual(reopened.language, 'cn')
        key(reopened, 28)
        key(reopened, 38)
        self.assertEqual(reopened.language, 'en')
        self.assertEqual(reopened.tr('代理无法建立 HTTPS 隧道（HTTP 502）'),
                         'Proxy could not establish an HTTPS tunnel (HTTP 502).')

    def test_reopen_checks_reachability_without_disconnecting(self):
        self.backend.active = True
        self.backend.reachable = False
        reopened = App(self.backend)
        settle(reopened)
        self.assertFalse(reopened.state['reachable'])
        self.assertTrue(self.backend.active)
        reopened.submit('status')
        settle(reopened)
        self.assertFalse(reopened.state['reachable'])
        self.assertEqual(self.backend.health_checks, 2)
        key(reopened, 28)
        settle(reopened)
        self.assertFalse(reopened.state['active'])

    def test_edit_protocol_and_save_on_return(self):
        key(self.app, 18)
        key(self.app, 106)
        self.assertEqual(self.app.edit['protocol'], 'http')
        key(self.app, 28)
        self.assertEqual(self.app.edit['protocol'], 'socks5')
        self.assertEqual(self.app.index, 0)
        key(self.app, 105)
        key(self.app, 1)
        settle(self.app)
        self.assertEqual(self.backend.config['protocol'], 'http')
        self.assertIsNone(self.app.edit)

    def test_fx_navigates_until_enter_begins_typing(self):
        key(self.app, 18)
        key(self.app, 45)
        self.assertEqual(self.app.index, 1)
        key(self.app, 28)
        for code in (33, 45, 91):
            key(self.app, code)
        self.assertTrue(self.app.edit['host'].endswith('fx.'))
        self.assertEqual(self.app.index, 1)
        key(self.app, 28)
        self.assertEqual(self.app.index, 1)
        key(self.app, 33)
        self.assertEqual(self.app.index, 0)

    def test_validation_failure_keeps_editor_and_displays_reason(self):
        self.backend.error = True
        key(self.app, 18)
        key(self.app, 1)
        settle(self.app)
        self.assertIsNotNone(self.app.edit)
        self.assertIn('请输入代理地址', self.app.message)

    def test_busy_does_not_freeze_exit(self):
        self.app.busy = True
        self.assertFalse(key(self.app, 1))

    def test_framebuffer_size_and_scroll(self):
        self.assertEqual(len(rgb565(self.app.draw())), 320*170*2)
        key(self.app, 18)
        for _ in range(4):
            key(self.app, 45)
        self.assertEqual(self.app.index, 4)
        self.assertEqual(self.app.draw().size, (320, 170))


if __name__ == '__main__':
    unittest.main()
