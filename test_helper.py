"""Exercise root-controller ownership and badge behavior without privileged operations."""
import os
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
        self.base, self.state, self.apps = root/'base', root/'state', root/'apps'
        for folder in (self.base, self.state, self.apps):
            folder.mkdir()
        (self.base/'lan-proxy.desktop').write_text(TEMPLATE)
        self.target = self.apps/'lan-proxy.desktop'
        self.target.write_text(TEMPLATE)
        def mapped_path(path):
            if path == '/usr/share/APPLaunch/applications/lan-proxy.desktop':
                return self.target
            return Path(path)
        for name, value in [('BASE', self.base), ('STATE', self.state), ('Path', mapped_path)]:
            patcher = patch.object(helper, name, value)
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

    def test_badge_update_is_atomic_and_restore_uses_template(self):
        replace = os.replace
        def observe(source, target):
            self.assertEqual(self.target.read_text(), TEMPLATE)
            self.assertIn('Name=LAN Proxy\n', Path(source).read_text())
            self.assertEqual(Path(source).stat().st_mode & 0o777, 0o644)
            replace(source, target)
        with patch.object(helper.os, 'replace', side_effect=observe):
            helper.badge(True)
        active = self.target.read_text()
        self.assertIn('Name[zh_CN]=局域网代理\n', active)
        self.assertIn('lan-proxy-active.png', active)
        helper.badge(False)
        self.assertEqual(self.target.read_text(), TEMPLATE)
        self.assertEqual(list(self.apps.glob('.lan-proxy-*')), [])

    def test_unchanged_badge_does_not_replace_file(self):
        with patch.object(helper.os, 'replace') as replace:
            helper.badge(False)
        replace.assert_not_called()

    def test_failed_atomic_update_preserves_existing_entry(self):
        with patch.object(helper.os, 'replace', side_effect=OSError('read only')):
            with self.assertRaises(OSError):
                helper.badge(True)
        self.assertEqual(self.target.read_text(), TEMPLATE)
        self.assertEqual(list(self.apps.glob('.lan-proxy-*')), [])

    def test_cleanup_without_ownership_only_restores_badge(self):
        helper.badge(True)
        helper.cleanup()
        self.assertEqual(self.commands, [])
        self.assertEqual(self.target.read_text(), TEMPLATE)

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

    def test_badge_failure_cannot_prevent_network_cleanup(self):
        marker = self.state/'owns-redirect'
        marker.touch()
        with patch.object(helper, 'badge', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                helper.cleanup()
        self.assertFalse(marker.exists())
        self.assertIn((helper.NFT, 'delete', 'table', 'inet', 'zproxy_lite'), self.commands)


if __name__ == '__main__':
    unittest.main()
