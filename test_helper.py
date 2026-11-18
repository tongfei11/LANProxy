"""Exercise root-controller ownership and badge behavior without privileged operations."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import helper

TEMPLATE = ('[Desktop Entry]\nName=LAN Proxy\nName[zh_CN]=局域网代理\n'
            'Icon=share/images/lan-proxy.png\n')


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.state = root / 'state'
        self.state.mkdir()
        patcher = patch.object(helper, 'STATE', self.state)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.commands = []
        def run(*args, **kwargs):
            self.commands.append(args)
            return SimpleNamespace(returncode=int('list' in args), stdout='')
        patcher = patch.object(helper, 'run', side_effect=run)
        self.mock_run = patcher.start()
        self.addCleanup(patcher.stop)

    def test_verification_retries_at_second_endpoint(self):
        self.mock_run.side_effect = [SimpleNamespace(returncode=28), SimpleNamespace(returncode=0)]
        helper.verify_transparent()
        self.assertEqual(self.mock_run.call_count, 2)
        self.assertEqual(self.mock_run.call_args.args[-1], 'https://example.org')

    def test_probe_distinguishes_failures_without_disclosing_raw_errors(self):
        cases = [
            ('http', 56, '407', 'sensitive', '认证失败'),
            ('http', 56, '403', 'sensitive', '拒绝 HTTPS'),
            ('http', 56, '502', 'sensitive', 'HTTP 502'),
            ('http', 7, '000', 'sensitive', '无法连接代理'),
            ('http', 28, '000', 'sensitive', '测试超时'),
            ('http', 60, '200', 'sensitive', 'HTTPS 验证失败'),
            ('socks5', 97, '000', 'User was rejected by the SOCKS5 server (1 1)', '认证失败'),
            ('socks5', 97, '000', 'sensitive', '握手失败'),
            ('http', 22, '200', 'sensitive', '测试网站失败'),
        ]
        for protocol, code, response, stderr, message in cases:
            with self.subTest(protocol=protocol, code=code, response=response):
                result = SimpleNamespace(returncode=code, stdout=response, stderr=stderr)
                with patch.object(helper, 'run', return_value=result):
                    data = dict(protocol=protocol, username='', password='', port=2080)
                    with self.assertRaisesRegex(ValueError, message) as error:
                        helper.probe(data, '192.168.1.2')
                    self.assertNotIn('sensitive', str(error.exception))

    def test_cleanup_without_marker_preserves_an_unowned_table(self):
        helper.cleanup()
        self.assertEqual(self.commands, [])

    def test_owned_cleanup_removes_table_and_marker(self):
        marker = self.state/'owns-redirect'
        marker.touch()
        helper.cleanup()
        self.assertIn((helper.NFT, 'delete', 'table', 'inet', 'zproxy_lite'), self.commands)
        self.assertFalse(marker.exists())

    def test_activate_rejects_unowned_existing_table(self):
        self.mock_run.side_effect = None
        self.mock_run.return_value = SimpleNamespace(returncode=0)
        with self.assertRaisesRegex(ValueError, '已存在'):
            helper.activate()
        self.assertFalse((self.state/'owns-redirect').exists())

    def test_activate_records_ownership(self):
        helper.activate()
        marker = self.state/'owns-redirect'
        self.assertTrue(marker.exists())
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

    def test_health_check_skips_network_when_proxy_is_off(self):
        self.assertEqual(helper.Controller().request({'action': 'check'}), {'active': False})
        self.mock_run.assert_not_called()

    def test_missing_firewall_reports_unreachable_without_stopping_relay(self):
        controller = helper.Controller()
        with patch.object(controller, 'is_active', return_value=True), \
             patch.object(controller, 'disconnect') as disconnect:
            result = controller.request({'action': 'check'})
        self.assertTrue(result['active'])
        self.assertFalse(result['reachable'])
        disconnect.assert_not_called()

    def test_local_control_protocol(self):
        import socket
        client, server = socket.socketpair()
        with client, server:
            client.sendall(b'{"action":"status"}\n')
            helper.dispatch(helper.Controller(), server)
            self.assertEqual(client.recv(128), b'{"active": false}\n')
            client.sendall(b'{"action":"unknown"}\n')
            helper.dispatch(helper.Controller(), server)
            self.assertIn(b'"error"', client.recv(128))


if __name__ == '__main__':
    unittest.main()
