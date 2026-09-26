#!/usr/bin/env python3
"""Daily systemd gate: run only when a local backup is due. No pruning or AWS."""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Etc/UTC')
ROOT = Path('/var/backups/homelab')
SCRIPTS = Path('/opt/aws-homelab-dr/scripts')
UPLOADER = SCRIPTS / 'lib/upload.py'
UTC = dt.timezone.utc
SERVICES = ('nextcloud','npm','pihole','plex')


def latest_complete(service, cadence, now):
    folder = ROOT/service
    if service != 'nextcloud':
        folder /= cadence
    dates = []
    if not folder.exists():
        return None
    for entry in folder.iterdir():
        if entry.name.startswith('.') or not entry.is_dir() or entry.is_symlink():
            continue
        if not (entry/'COMPLETE').is_file() or not (entry/'SHA256SUMS').is_file():
            continue
        try:
            manifest = json.loads((entry/'manifest.json').read_text())
            if manifest.get('service') != service:
                continue
            if service != 'nextcloud' and manifest.get('cadence') != cadence:
                continue
            files = manifest['files']
            if not files or not all(Path(f['name']).name == f['name'] and
                                    (entry/f['name']).is_file() for f in files):
                continue
            stamp = dt.datetime.fromisoformat(manifest['validated_at_utc'].replace('Z','+00:00'))
            if stamp.tzinfo is None or stamp > now:
                continue
            dates.append(stamp)
        except (OSError,ValueError,KeyError,TypeError):
            continue
    return max(dates) if dates else None


def decision(service, now, critical, monthly=None):
    today = now.astimezone(ZONE).date()
    # Monthly includes all critical Plex state, so it also satisfies its 15-day policy.
    if service == 'plex':
        if monthly is None or (monthly.astimezone(ZONE).year,monthly.astimezone(ZONE).month) < (today.year,today.month):
            return 'monthly'
        critical = max([t for t in (critical,monthly) if t is not None],default=None)
    if critical is None or today >= critical.astimezone(ZONE).date() + dt.timedelta(days=15):
        return 'biweekly'
    return 'not-due'


def inspect(service):
    now = dt.datetime.now(UTC)
    critical = latest_complete(service,'biweekly',now)
    monthly = latest_complete(service,'monthly',now) if service=='plex' else None
    result = decision(service,now,critical,monthly)
    print('Service: '+service+'; timezone: Etc/UTC',flush=True)
    print('Latest critical backup: '+(critical.isoformat() if critical else 'none'),flush=True)
    if service=='plex':
        print('Latest monthly backup: '+(monthly.isoformat() if monthly else 'none'),flush=True)
    print('Action due: '+result,flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('service',choices=SERVICES)
    parser.add_argument('--status',action='store_true',help='Read completion markers only; never run a backup.')
    args=parser.parse_args()
    if os.geteuid()!=0:
        parser.error('Run with sudo on the target VM.')
    if args.status:
        inspect(args.service)
        return 0
    with open('/run/aws-homelab-schedule-'+args.service+'.lock','w') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another scheduling check is active.',file=sys.stderr)
            return 1
        due=inspect(args.service)
        if due=='not-due':
            return 0
        # Verify credentials and bucket access before making an application-consistent copy.
        access=subprocess.run(['/usr/bin/python3',str(UPLOADER),args.service,'--check'])
        if access.returncode:
            print('Upload check failed; no new local backup was created.',file=sys.stderr)
            return access.returncode if access.returncode >= 0 else 1
        command=['/bin/bash',str(SCRIPTS/args.service/'backup.sh'),'--run']
        if due=='monthly':
            command.append('--monthly')
        # Capture the published set path so only this successfully completed set is uploaded.
        result=subprocess.run(command,text=True,capture_output=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        if result.returncode:
            print('Backup failed. Previous completed sets remain unchanged; inspect journal.',file=sys.stderr)
            return result.returncode if result.returncode>=0 else 1
        matches=[line.removeprefix('Backup complete: ').strip() for line in result.stdout.splitlines()
                 if line.startswith('Backup complete: ')]
        if len(matches) != 1:
            print('Backup completed without a usable output path; nothing uploaded.',file=sys.stderr)
            return 1
        transfer=subprocess.run(['/usr/bin/python3',str(UPLOADER),args.service,'--path',matches[0]])
        if transfer.returncode:
            print('Upload failed. The completed local set was retained; inspect journal.',file=sys.stderr)
        return transfer.returncode if transfer.returncode >= 0 else 1


if __name__=='__main__':
    sys.exit(main())
