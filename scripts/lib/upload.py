#!/usr/bin/env python3
"""Upload one completed backup set to S3, preserving its local integrity checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path('/var/backups/homelab')
CONFIG = Path('/etc/aws-homelab-dr/upload.env')
SERVICES = ('nextcloud', 'npm', 'pihole', 'plex')
BUCKET_RE = re.compile(r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def config():
    require(CONFIG.is_file() and not CONFIG.is_symlink(), 'Missing upload configuration: ' + str(CONFIG))
    info = CONFIG.stat()
    require(info.st_uid == 0 and not stat.S_IMODE(info.st_mode) & 0o077,
            'Upload configuration must be owned by root and mode 600.')
    values = {}
    for line in CONFIG.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, marker, value = line.partition('=')
        require(marker and key == 'AWS_HOMELAB_DR_BUCKET', 'Invalid upload configuration.')
        values[key] = value.strip()
    bucket = values.get('AWS_HOMELAB_DR_BUCKET', '')
    require(BUCKET_RE.fullmatch(bucket) is not None, 'Invalid S3 bucket name in upload configuration.')
    return bucket


def aws(*args, capture=False):
    result = subprocess.run(['aws', '--no-cli-pager', *args], text=True,
                            capture_output=capture, timeout=900)
    if result.returncode:
        raise RuntimeError('AWS command failed; check the restricted credentials and network connection.')
    return result.stdout


def verify_set(service, folder):
    require(not folder.is_symlink(), 'Backup set must not be a symlink.')
    folder = folder.resolve(strict=True)
    allowed_root = (ROOT / service).resolve(strict=False)
    require(folder.parent == allowed_root or folder.parent.parent == allowed_root,
            'Backup set must belong to the expected service directory.')
    require(folder.is_dir() and not folder.is_symlink(), 'Backup set is not a real directory.')
    require((folder / 'COMPLETE').is_file(), 'Backup set is not marked complete.')
    try:
        manifest = json.loads((folder / 'manifest.json').read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError('Invalid backup manifest.') from exc
    require(manifest.get('service') == service, 'Backup manifest service does not match.')
    cadence = manifest.get('cadence', 'biweekly')
    require(cadence in ('biweekly', 'monthly'), 'Invalid backup cadence.')
    payload = []
    for item in manifest.get('files', []):
        name = item.get('name') if isinstance(item, dict) else None
        require(isinstance(name, str) and Path(name).name == name, 'Invalid manifest filename.')
        path = folder / name
        require(path.is_file() and not path.is_symlink(), 'Missing backup payload: ' + name)
        require(item.get('bytes') == path.stat().st_size and item.get('sha256') == digest(path),
                'Backup payload checksum mismatch: ' + name)
        payload.append(path)
    require(bool(payload), 'Backup manifest has no payload.')
    sums = folder / 'SHA256SUMS'
    require(sums.is_file() and not sums.is_symlink(), 'Missing SHA256SUMS.')
    expected = {path.name: digest(path) for path in [*payload, folder / 'manifest.json']}
    recorded = {}
    for line in sums.read_text().splitlines():
        value, separator, name = line.partition('  ')
        require(separator and re.fullmatch(r'[0-9a-f]{64}', value) and Path(name).name == name,
                'Invalid SHA256SUMS entry.')
        recorded[name] = value
    require(recorded == expected, 'SHA256SUMS does not match the completed payload.')
    return cadence, [*payload, folder / 'manifest.json', sums, folder / 'COMPLETE']


def check_access(bucket):
    require(os.geteuid() == 0, 'Run with sudo on the target VM.')
    require(shutil_which('aws'), 'AWS CLI is not installed.')
    aws('s3api', 'get-bucket-location', '--bucket', bucket)


def shutil_which(name):
    for directory in os.environ.get('PATH', '').split(os.pathsep):
        path = Path(directory) / name
        if path.is_file() and os.access(path, os.X_OK):
            return True
    return False


def upload(bucket, service, folder):
    cadence, files = verify_set(service, folder)
    prefix = '/'.join((service, cadence, folder.name))
    for path in files:
        checksum = digest(path)
        target = 's3://' + bucket + '/' + prefix + '/' + path.name
        aws('s3', 'cp', str(path), target, '--only-show-errors',
            '--metadata', 'sha256=' + checksum)
        remote = json.loads(aws('s3api', 'head-object', '--bucket', bucket,
                                '--key', prefix + '/' + path.name, capture=True))
        require(remote.get('ContentLength') == path.stat().st_size and
                remote.get('Metadata', {}).get('sha256') == checksum,
                'Remote verification failed: ' + path.name)
    print('Uploaded and verified: s3://' + bucket + '/' + prefix + '/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=SERVICES)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--check', action='store_true', help='Verify local configuration and S3 access only.')
    actions.add_argument('--path', type=Path, help='Completed local backup set to upload.')
    args = parser.parse_args()
    try:
        bucket = config()
        check_access(bucket)
        if args.check:
            print('Upload prerequisites and restricted S3 access verified.')
        else:
            upload(bucket, args.service, args.path)
        return 0
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
