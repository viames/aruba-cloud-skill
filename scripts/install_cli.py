#!/usr/bin/env python3
"""Install the checksum-pinned official Aruba Cloud CLI locally to this skill."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def platform_key():
    system = {'Darwin': 'darwin', 'Linux': 'linux'}.get(platform.system())
    arch = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'amd64', 'AMD64': 'amd64'}.get(platform.machine())
    if not system or not arch:
        raise ValueError('Supported: macOS/Linux, arm64/amd64')
    return f'{system}_{arch}'


def extract_binary(data):
    # Read only the named regular executable; never extract archive paths.
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        members = [m for m in archive.getmembers() if Path(m.name).name == 'acloud' and m.isfile()]
        if len(members) != 1 or members[0].size > 100 * 1024 * 1024:
            raise ValueError('Unexpected release archive')
        with archive.extractfile(members[0]) as stream:
            return stream.read()


def atomic_write(path, data, mode):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.install-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            os.fchmod(stream.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    manifest = json.loads((ROOT / 'references/provenance.json').read_text())
    target = platform_key()
    artifact = manifest['artifacts'][target]
    url = f"https://github.com/Arubacloud/acloud-cli/releases/download/v{manifest['cli_version']}/{artifact['filename']}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(30 * 1024 * 1024 + 1)
    if len(data) > 30 * 1024 * 1024:
        raise ValueError('Release archive exceeds size limit')
    if hashlib.sha256(data).hexdigest() != artifact['sha256']:
        raise ValueError('Archive SHA-256 mismatch; nothing installed')
    binary = extract_binary(data)
    folder = ROOT / 'bin'
    folder.mkdir(exist_ok=True)
    if folder.is_symlink():
        raise ValueError('Refusing a symlinked bin directory')
    receipt = {'platform': target, 'cli_version': manifest['cli_version'],
               'archive_sha256': artifact['sha256'],
               'binary_sha256': hashlib.sha256(binary).hexdigest()}
    atomic_write(folder / 'acloud', binary, 0o755)
    atomic_write(folder / 'install.json', (json.dumps(receipt, indent=2)+'\n').encode(), 0o644)
    print(f"Installed official acloud {manifest['cli_version']} ({target}); SHA-256 verified")


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        raise SystemExit(f'Installation failed: {error}') from None
