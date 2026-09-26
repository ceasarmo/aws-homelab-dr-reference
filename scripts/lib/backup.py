#!/usr/bin/env python3
"""Local application backups for the inventoried Ubuntu VMs. Standard library only."""
import argparse
import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
import native_backups

PLEX = Path('/var/lib/plexmediaserver/Library/Application Support/Plex Media Server')
PLEX_SQLITE = '/usr/lib/plexmediaserver/Plex SQLite'
NPM_CONTAINER = 'npm_app_1'
ZIP_DIRS = {
    'radarr': Path('/var/lib/radarr/Backups'),
    'sonarr': Path('/var/lib/sonarr/Backups'),
    'prowlarr': Path('/var/lib/prowlarr/Backups'),
    'bazarr': Path('/opt/bazarr/data/backup'),
}
MAX_ZIP_AGE = 3600  # Generate fresh native backups before running Plex.
PI_TABLES = ('adlist', 'domainlist', 'group', 'client', 'adlist_by_group',
             'domainlist_by_group', 'client_by_group')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(*args, log=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    if log:
        with log.open('a') as f:
            f.write(result.stderr)
    require(result.returncode == 0, 'Command failed: ' + Path(args[0]).name)
    return result.stdout.strip()


def paths_for(service, monthly=False):
    if service == 'npm':
        return [Path('/root/npm/docker-compose.yml'), Path('/root/npm/data/keys.json'),
                Path('/root/npm/data/nginx')]
    if service == 'pihole':
        return [Path('/etc/pihole/pihole.toml'), Path('/etc/pihole/dnsmasq.conf'),
                Path('/etc/pihole/hosts/custom.list')]
    paths = [PLEX / 'Preferences.xml', Path('/etc/samba/smb.conf'), Path('/etc/fstab'),
             Path('/etc/systemd/system/bazarr.service'),
             Path('/etc/systemd/system/flaresolverr.service'),
             Path('/home/qbittorrent/.config/qBittorrent'),
             Path('/home/qbittorrent/.local/share/qBittorrent')]
    if monthly:
        paths += [PLEX / 'Metadata', PLEX / 'Media']
    return paths


def validate_paths(paths):
    # Refuse symlinks rather than silently omit or follow external content.
    for root in paths:
        require(root.exists() and not root.is_symlink(), 'Missing path or symlink: ' + str(root))
        entries = [root]
        if root.is_dir():
            entries.extend(root.rglob('*'))
        for p in entries:
            mode = p.lstat().st_mode
            require(not stat.S_ISLNK(mode), 'Symlink requires review: ' + str(p))
            require(stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISSOCK(mode),
                    'Special file requires review: ' + str(p))


def archive(destination, paths):
    validate_paths(paths)
    def selected(info):
        if info.issym() or info.islnk():
            raise RuntimeError('Link appeared during backup.')
        require(info.isfile() or info.isdir(), 'Unsupported archive member.')
        return info
    with tarfile.open(destination, 'w:gz', dereference=False) as tar:
        for path in paths:
            # Add entries individually: intentionally skip qBittorrent IPC sockets.
            entries = [path] + (sorted(path.rglob('*')) if path.is_dir() else [])
            for entry in entries:
                if stat.S_ISSOCK(entry.lstat().st_mode):
                    continue
                tar.add(entry, arcname=str(entry).lstrip('/'), recursive=False, filter=selected)
    with tarfile.open(destination, 'r:gz') as tar:
        for member in tar:
            if member.isfile():
                with tar.extractfile(member) as f:
                    while f.read(1024 * 1024):
                        pass
    # Read the gzip trailer as well (tar end markers may precede gzip EOF).
    with gzip.open(destination, 'rb') as f:
        while f.read(1024 * 1024):
            pass


def snapshot(source, destination):
    require(source.is_file(), 'SQLite source missing.')
    deadline = time.monotonic() + 60
    def progress(*_):
        require(time.monotonic() < deadline, 'SQLite snapshot timed out.')
    with contextlib.closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with contextlib.closing(sqlite3.connect(str(destination))) as dst:
            src.backup(dst, pages=256, progress=progress)
            require(dst.execute('PRAGMA integrity_check').fetchall() == [('ok',)],
                    'SQLite integrity check failed.')


def export_pihole(source, destination):
    require(source.is_file(), 'Pi-hole gravity database missing.')
    deadline = time.monotonic() + 60
    def progress(*_):
        require(time.monotonic() < deadline, 'SQLite snapshot timed out.')
    with contextlib.closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with contextlib.closing(sqlite3.connect(':memory:')) as db:
            src.backup(db, pages=256, progress=progress)
            require(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)],
                    'Pi-hole database integrity check failed.')
            tables = {}
            for name in PI_TABLES:
                cursor = db.execute('SELECT * FROM "' + name + '"')
                columns = [c[0] for c in cursor.description]
                tables[name] = {'columns': columns, 'rows': cursor.fetchall()}
            destination.write_text(json.dumps({'schema_version': 1,
                'format': 'homelab-logical-export-not-teleporter', 'tables': tables}, indent=2) + '\n')
    json.loads(destination.read_text())


def latest_zips():
    selected = {}
    now = time.time()
    for name, folder in ZIP_DIRS.items():
        # Native manual and scheduled backups are eligible; update snapshots are not.
        candidates = [folder, folder/'manual', folder/'scheduled']
        files = [p for directory in candidates if not directory.is_symlink()
                 for p in directory.glob('*.zip') if p.is_file() and not p.is_symlink()]
        require(bool(files), 'Native ZIP missing: ' + name)
        path = max(files, key=lambda p: p.stat().st_mtime)
        age = now - path.stat().st_mtime
        require(0 <= age <= MAX_ZIP_AGE, 'Generate a fresh native ZIP (within 1 hour): ' + name)
        with zipfile.ZipFile(path) as z:
            require(bool(z.namelist()) and z.testzip() is None, 'Invalid ZIP: ' + name)
        selected[name] = path
    return selected


def safe_destination(root):
    existing = root
    while not existing.exists():
        require(not existing.is_symlink(), 'Destination contains a dangling symlink.')
        existing = existing.parent
    require(existing.is_dir() and existing.resolve() == existing, 'Unsafe backup destination.')
    for p in [existing, *existing.parents]:
        st = p.stat()
        require(st.st_uid == 0 and not stat.S_IMODE(st.st_mode) & 0o022,
                'Backup parents must be root-owned and not group/world writable.')
    return existing


def service_state(service):
    state = command('systemctl', 'show', service, '--property=ActiveState', '--value')
    require(state in ('active', 'inactive'), 'Service requires review: ' + service)
    return state


def preflight(service, monthly, root):
    require(sys.platform.startswith('linux') and os.geteuid() == 0, 'Run with sudo on the Ubuntu VM.')
    for cmd in (['docker'] if service == 'npm' else ['pihole'] if service == 'pihole'
                else ['systemctl', 'dpkg-query', PLEX_SQLITE]):
        require(shutil.which(cmd) is not None, 'Missing dependency: ' + cmd)
    paths = paths_for(service, monthly)
    validate_paths(paths)
    parent = safe_destination(root)
    minimum = 2 * 1024**3 if monthly else 256 * 1024**2
    # Monthly space scales with uncompressed metadata instead of relying only on the old measurement.
    if monthly:
        size = sum(p.stat().st_size for base in (PLEX/'Metadata', PLEX/'Media')
                   for p in base.rglob('*') if p.is_file())
        minimum = max(minimum, size + 256 * 1024**2)
    require(shutil.disk_usage(parent).free >= minimum, 'Insufficient free backup space.')
    if service == 'npm':
        data = json.loads(command('docker', 'inspect', NPM_CONTAINER))[0]
        require(data['State']['Running'], 'NPM must be running before backup.')
        mounts = {m['Destination']: m['Source'] for m in data['Mounts']}
        require(mounts.get('/data') == '/root/npm/data', 'Unexpected NPM data mount.')
        require(Path('/root/npm/data/database.sqlite').is_file(), 'NPM SQLite missing.')
    elif service == 'pihole':
        require(Path('/etc/pihole/gravity.db').is_file(), 'Pi-hole SQLite missing.')
    else:
        for name in ('com.plexapp.plugins.library.db', 'com.plexapp.plugins.library.blobs.db'):
            require((PLEX/'Plug-in Support/Databases'/name).is_file(), 'Plex SQLite missing.')
        native_backups.check_all()
        for unit in ('plexmediaserver', 'qbittorrent-nox'):
            service_state(unit)


@contextlib.contextmanager
def paused(service, log):
    restart = []
    try:
        if service == 'npm':
            require(command('docker','inspect','--format={{.State.Running}}',NPM_CONTAINER) == 'true',
                    'NPM state changed before capture.')
            restart.append(('docker', NPM_CONTAINER))
            command('docker', 'stop', '--time=30', NPM_CONTAINER, log=log)
            require(command('docker','inspect','--format={{.State.Running}}',NPM_CONTAINER) == 'false',
                    'NPM did not stop.')
        elif service == 'plex':
            for unit in ('plexmediaserver', 'qbittorrent-nox'):
                if service_state(unit) == 'active':
                    restart.append(('systemctl', unit))
                    command('systemctl', 'stop', unit, log=log)
                    require(service_state(unit) == 'inactive', 'Service did not stop: ' + unit)
        yield
    finally:
        # Ignore additional TERM/INT during bounded recovery; restore handlers afterward.
        handlers = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGTERM, signal.SIGINT)}
        failures = []
        try:
            for kind, name in reversed(restart):
                try:
                    command(kind, 'start', name, log=log)
                    if kind == 'systemctl':
                        require(service_state(name) == 'active', 'Service failed to start.')
                    else:
                        require(command('docker','inspect','--format={{.State.Running}}',name) == 'true',
                                'NPM failed to start.')
                except Exception:
                    failures.append(name)
        finally:
            for s, handler in handlers.items():
                signal.signal(s, handler)
        require(not failures, 'Manual service recovery required: ' + ', '.join(failures))


def capture(service, monthly, work):
    log = work / 'backup.log'
    zips = native_backups.generate(work, ZIP_DIRS) if service == 'plex' else {}
    if service == 'plex':
        (work/'packages.txt').write_text(command('dpkg-query','-W','-f=${binary:Package}\t${Version}\n',log=log)+'\n')
        states={s:service_state(s) for s in ('plexmediaserver','qbittorrent-nox')}
        (work/'service-state.json').write_text(json.dumps(states,indent=2)+'\n')
    with paused(service, log):
        archive(work/'config.tar.gz', paths_for(service, False))
        if service == 'npm':
            snapshot(Path('/root/npm/data/database.sqlite'), work/'database.sqlite')
            (work/'container.txt').write_text(command('docker', 'inspect',
                '--format={{.Name}} {{.Config.Image}} {{.Image}}', NPM_CONTAINER) + '\n')
        elif service == 'pihole':
            export_pihole(Path('/etc/pihole/gravity.db'), work/'rules.json')
            (work/'version.txt').write_text(command('pihole','-v',log=log) + '\n')
        else:
            dbdir = PLEX/'Plug-in Support/Databases'
            for source, dest in [('com.plexapp.plugins.library.db','plex-library.sqlite'),
                                 ('com.plexapp.plugins.library.blobs.db','plex-blobs.sqlite')]:
                command(PLEX_SQLITE, '-readonly', str(dbdir/source),
                        ".backup '" + str(work/dest) + "'", log=log)
                require(command(PLEX_SQLITE, '-readonly', str(work/dest),
                                'PRAGMA integrity_check;', log=log) == 'ok', 'Plex integrity failed.')
            records = {}
            for name, source in zips.items():
                before = source.stat()
                if source != work/(name+'.zip'):
                    shutil.copyfile(source, work/(name+'.zip'))
                after = source.stat()
                require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                        'Native ZIP changed during capture.')
                with zipfile.ZipFile(work/(name+'.zip')) as z:
                    require(z.testzip() is None, 'Copied ZIP failed validation.')
                records[name] = {'source_modified_utc':dt.datetime.fromtimestamp(before.st_mtime,dt.timezone.utc).isoformat(),
                                 'age_seconds_at_capture':time.time()-before.st_mtime}
            (work/'native-backups.json').write_text(json.dumps(records,indent=2)+'\n')
            if monthly:
                archive(work/'metadata.tar.gz', [PLEX/'Metadata', PLEX/'Media'])


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def finish(work, service, monthly, started):
    files = [{'name':p.name, 'bytes':p.stat().st_size, 'sha256':digest(p)}
             for p in sorted(work.iterdir()) if p.is_file() and p.name != 'backup.log']
    require(bool(files), 'No payload generated.')
    manifest = {'schema_version':1,'service':service,'cadence':'monthly' if monthly else 'biweekly',
                'started_at_utc':started,'validated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                'restore_test':'pending','user_files_included':False,'files':files}
    (work/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    sums = [(item['sha256'],item['name']) for item in files]
    sums.append((digest(work/'manifest.json'),'manifest.json'))
    (work/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for h,n in sums))
    for h, name in sums:
        require(digest(work/name) == h, 'Checksum verification failed.')
    (work/'COMPLETE').write_text('Local validation passed; restoration pending.\n')
    final = work.with_name(work.name.removeprefix('.incomplete-'))
    require(not final.exists(), 'Destination collision.')
    work.rename(final)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service', choices=['npm','pihole','plex'])
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--run', action='store_true')
    parser.add_argument('--monthly', action='store_true', help='Plex only: include metadata with paired DB/config.')
    args = parser.parse_args()
    if args.monthly and args.service != 'plex':
        parser.error('--monthly is only valid for Plex')
    if not args.check and not args.run:
        parser.print_help()
        return 0
    root = Path('/var/backups/homelab') / args.service / ('monthly' if args.monthly else 'biweekly')
    os.umask(0o077)
    work = None
    try:
        preflight(args.service, args.monthly, root)
        if args.check:
            print('Prerequisites OK; no backup or service changes.')
            return 0
        # Same Plex lock for monthly and biweekly backups.
        with open('/run/aws-homelab-dr-'+args.service+'.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def interrupted(*_):
                raise RuntimeError('Interrupted.')
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, interrupted)
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(root, 0o700)
            started = dt.datetime.now(dt.timezone.utc).isoformat()
            prefix = '.incomplete-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'
            work = Path(tempfile.mkdtemp(prefix=prefix,dir=root))
            capture(args.service, args.monthly, work)
            final = finish(work,args.service,args.monthly,started)
            print('Backup complete: '+str(final))
            print('No AWS actions, scheduling, retention or deletion performed.')
        return 0
    except Exception as exc:
        # Never print subprocess stdout, DB rows or configuration to the console.
        if work:
            print('Incomplete backup retained: '+str(work),file=sys.stderr)
        print('ERROR: '+str(exc) if isinstance(exc,RuntimeError) else
              'ERROR: '+type(exc).__name__+'; check local paths, permissions and private log.',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
