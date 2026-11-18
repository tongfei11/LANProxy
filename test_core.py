import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import core

class Configuration(unittest.TestCase):
    def data(self, **kwargs):
        return dict(core.DEFAULT, host='192.168.1.50', **kwargs)

    def test_rejects_invalid_configuration(self):
        for update in ({'host': ''}, {'host': 'http://host'}, {'port': 0}, {'port': 65536},
                       {'protocol': 'exec'}, {'username': 'user\n'}, {'port': True}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                core.validate(dict(self.data(), **update))

    def test_lan_only_resolution(self):
        for ip, allowed in [('192.168.1.50', True), ('127.0.0.1', False), ('8.8.8.8', False)]:
            with patch('core.socket.getaddrinfo', return_value=[(2, 1, 6, '', (ip, 0))]):
                if allowed: self.assertEqual(core.resolve_lan('proxy'), ip)
                else:
                    with self.assertRaises(ValueError): core.resolve_lan('proxy')

    def test_config_quotes_credentials_and_selects_protocol(self):
        config = core.redsocks_config(self.data(username='u";', password='p\\q'), '192.168.1.50')
        self.assertIn('type = http-connect;', config)
        self.assertIn('login = ' + json.dumps('u";') + ';', config)
        self.assertIn('password = ' + json.dumps('p\\q') + ';', config)
        config = core.redsocks_config(self.data(protocol='socks5'), '192.168.1.50')
        self.assertIn('type = socks5;', config)
        self.assertNotIn('password =', config)

    def test_atomic_secret_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            core.atomic_json(path, self.data(password='secret'))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())['password'], 'secret')
            self.assertEqual(list(Path(tmp).iterdir()), [path])

if __name__ == '__main__': unittest.main()
