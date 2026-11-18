"""Sync the optional admin badge from a boolean runtime marker."""
import os
from pathlib import Path
import tempfile

TEMPLATE = Path('/usr/lib/lan-proxy/lan-proxy.desktop')
ENTRY = Path('/usr/share/APPLaunch/applications/lan-proxy.desktop')
FORWARDING = Path('/run/lan-proxy/forwarding')


def sync(template, entry, active):
    text = template.read_text()
    if active:
        text = text.replace('Icon=share/images/lan-proxy.png',
                            'Icon=share/images/lan-proxy-active.png')
    if entry.exists() and entry.read_text() == text:
        return
    with tempfile.NamedTemporaryFile(mode='w', dir=entry.parent, prefix='.lan-proxy-',
                                     delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(text)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            temporary.replace(entry)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    sync(TEMPLATE, ENTRY, FORWARDING.exists())
