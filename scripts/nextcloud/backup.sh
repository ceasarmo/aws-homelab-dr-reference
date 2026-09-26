#!/usr/bin/env bash
# Ubuntu reference implementation. Never source this file or execute it with bash -x.
set -Eeuo pipefail
umask 077
export LC_ALL=C

APP_DIR=/var/www/nextcloud-app
BACKUP_ROOT=/var/backups/homelab/nextcloud
DB_NAME=nextcloud
WEB_USER=www-data
MIN_FREE_KIB=262144
LOCK_FILE=/run/aws-homelab-dr-nextcloud.lock
MODE=${1:---help}

usage() {
    cat <<'HELP'
Usage: sudo bash scripts/nextcloud/backup.sh --check|--run
  --check  Read-only prerequisite checks; no backup or maintenance changes.
  --run    Local DB/config backup, brief maintenance mode, integrity + SHA-256.
  --help   Show this help (default).
No AWS access, scheduling, deletion, retention, or user-file backup.
HELP
}
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
occ() { runuser -u "$WEB_USER" -- php "$APP_DIR/occ" "$@"; }

[[ $# -le 1 ]] || { usage >&2; exit 2; }
case "$MODE" in
    --help|-h) usage; exit 0 ;;
    --check|--run) ;;
    *) usage >&2; exit 2 ;;
esac
[[ $(uname -s) == Linux ]] || fail 'Run on the Ubuntu Nextcloud VM.'
[[ $EUID -eq 0 ]] || fail 'Root is required (sudo).'
for cmd in runuser php python3 mariadb mariadb-dump gzip tar sha256sum flock \
           dpkg-query df awk install mktemp date stat realpath mv; do
    command -v "$cmd" >/dev/null || fail "Missing dependency: $cmd"
done
[[ -f "$APP_DIR/occ" && -d "$APP_DIR/config" ]] || fail 'Nextcloud installation not found.'
[[ -f "$APP_DIR/config/config.php" ]] || fail 'Nextcloud config.php not found.'
# Do not follow a config symlink into user data or other unexpected directories.
python3 - "$APP_DIR/config" <<'PYCONFIG'
import os, sys
from pathlib import Path
root=Path(sys.argv[1])
if root.is_symlink(): sys.exit('Config symlinks require manual review.')
for directory, dirs, files in os.walk(root):
    for name in dirs + files:
        if (Path(directory)/name).is_symlink():
            sys.exit('Config symlinks require manual review.')
PYCONFIG
for file in /etc/apache2/sites-enabled/nextcloud.conf /etc/fstab /etc/samba/smb.conf; do
    [[ -r "$file" ]] || fail "Required configuration unavailable: $file"
done
# Never read passwords from config.php or command-line arguments.
[[ $(occ config:system:get dbtype) == mysql ]] || fail 'Expected MariaDB/MySQL.'
[[ $(occ config:system:get dbname) == "$DB_NAME" ]] || fail 'Unexpected database name.'
case "$(occ config:system:get dbhost)" in
    localhost|127.0.0.1|localhost:3306|127.0.0.1:3306) ;;
    *) fail 'Only the inventoried local MariaDB is supported.' ;;
esac
STATUS=$(occ status --output=json)
printf '%s' "$STATUS" | python3 -c '
import json,sys
s=json.load(sys.stdin)
if not s.get("installed") or s.get("maintenance") or s.get("needsDbUpgrade"):
    sys.exit("Nextcloud must be installed, outside maintenance mode, and up to date.")
' || fail 'Nextcloud is not ready; existing maintenance mode is preserved.'
mariadb --no-defaults --user=root --protocol=socket --database="$DB_NAME" \
    --batch --skip-column-names --execute='SELECT 1' >/dev/null 2>&1 \
    || fail 'Local root socket database access failed; no credentials were changed.'
# Validate existing ancestors before creating any directory or opening a log.
parent=$BACKUP_ROOT
while [[ ! -e "$parent" ]]; do
    [[ ! -L "$parent" ]] || fail 'Backup path contains a dangling symlink.'
    parent=${parent%/*}
done
[[ -d "$parent" && $(realpath "$parent") == "$parent" ]] \
    || fail 'Backup path must use real directories, not symlinks.'
python3 - "$parent" <<'PY'
import os, stat, sys
from pathlib import Path
p=Path(sys.argv[1])
for directory in [p, *p.parents]:
    info=directory.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
        sys.exit('Backup ancestors must be root-owned and not group/world writable.')
PY
available=$(df -Pk "$parent" | awk 'END {print $4}')
[[ "$available" =~ ^[0-9]+$ && "$available" -ge "$MIN_FREE_KIB" ]] \
    || fail 'At least 256 MiB free is required; actual backup may need more.'
if [[ "$MODE" == --check ]]; then
    printf 'Prerequisites OK. No backup created; no maintenance mode changed.\n'
    exit 0
fi

# Serialize this script. External maintenance/backup jobs must not overlap it.
exec 9>"$LOCK_FILE"
flock -n 9 || fail 'Another Nextcloud backup is running.'
install -d -m 700 "$BACKUP_ROOT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
WORK_DIR=$(mktemp -d "$BACKUP_ROOT/.incomplete-$STAMP-XXXXXX")
LOG="$WORK_DIR/backup.log"
MAINTENANCE_OWNED=0
cleanup() {
    result=$?
    trap - EXIT INT TERM
    if [[ "$MAINTENANCE_OWNED" == 1 ]]; then
        if ! occ maintenance:mode --off >>"$LOG" 2>&1; then
            printf 'ERROR: Maintenance could not be disabled; inspect the VM and private log.\n' >&2
            result=1
        fi
    fi
    if [[ "$result" != 0 ]]; then
        printf 'Backup incomplete. Retained for inspection: %s\n' "$WORK_DIR" >&2
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Recheck after acquiring the lock to avoid acting on stale application status.
STATUS=$(occ status --output=json 2>>"$LOG")
printf '%s\n' "$STATUS" >"$WORK_DIR/nextcloud-status.json"
python3 - "$WORK_DIR/nextcloud-status.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]))
if not s.get('installed') or s.get('maintenance') or s.get('needsDbUpgrade'):
    sys.exit('Nextcloud state changed; aborting without changing maintenance mode.')
PY
occ app:list --output=json >"$WORK_DIR/nextcloud-apps.json" 2>>"$LOG"
dpkg-query -W -f='${binary:Package}\t${Version}\n' >"$WORK_DIR/packages.txt" 2>>"$LOG"
# Set ownership before toggling so a partial failure still triggers cleanup.
MAINTENANCE_OWNED=1
occ maintenance:mode --on >>"$LOG" 2>&1
mariadb-dump --no-defaults --user=root --protocol=socket \
    --single-transaction --quick --routines --triggers --hex-blob \
    "$DB_NAME" 2>>"$LOG" | gzip -9 >"$WORK_DIR/nextcloud-db.sql.gz"
# Dereference the Apache sites-enabled link so the actual configuration is saved.
# Config-directory symlinks were rejected by preflight.
tar --dereference -czf "$WORK_DIR/nextcloud-config.tar.gz" -C / \
    var/www/nextcloud-app/config \
    etc/apache2/sites-enabled/nextcloud.conf etc/fstab etc/samba/smb.conf \
    >>"$LOG" 2>&1
occ maintenance:mode --off >>"$LOG" 2>&1
MAINTENANCE_OWNED=0

[[ -s "$WORK_DIR/nextcloud-db.sql.gz" ]] || fail 'Database archive is empty.'
gzip -t "$WORK_DIR/nextcloud-db.sql.gz" 2>>"$LOG"
# Reject an empty decompressed dump without exposing its contents.
python3 - "$WORK_DIR/nextcloud-db.sql.gz" <<'PY'
import gzip,sys
with gzip.open(sys.argv[1], 'rb') as f:
    if not f.read(1): sys.exit('Empty database dump.')
PY
tar -tzf "$WORK_DIR/nextcloud-config.tar.gz" >/dev/null 2>>"$LOG"
python3 - "$WORK_DIR" <<'PY'
from pathlib import Path
import datetime, hashlib, json, sys
root=Path(sys.argv[1])
for name in ('nextcloud-status.json','nextcloud-apps.json'):
    json.loads((root/name).read_text())
files=[]
for name in ('nextcloud-db.sql.gz','nextcloud-config.tar.gz',
             'nextcloud-status.json','nextcloud-apps.json','packages.txt'):
    p=root/name
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''): h.update(block)
    files.append({'name':name,'bytes':p.stat().st_size,'sha256':h.hexdigest()})
manifest={'schema_version':1,'service':'nextcloud',
          'validated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope':'database and configuration only; user files excluded',
          'restore_test':'pending','files':files}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
PY
(
    cd "$WORK_DIR"
    sha256sum nextcloud-db.sql.gz nextcloud-config.tar.gz nextcloud-status.json \
        nextcloud-apps.json packages.txt manifest.json > SHA256SUMS
    sha256sum --check SHA256SUMS >>"$LOG" 2>&1
)
# Complete only after checks and maintenance cleanup succeed. No old copies removed.
printf 'Validated locally; restore test pending.\n' >"$WORK_DIR/COMPLETE"
FINAL_DIR="$BACKUP_ROOT/${WORK_DIR##*/}"
FINAL_DIR=${FINAL_DIR/\.incomplete-/}
[[ ! -e "$FINAL_DIR" ]] || fail 'Unexpected destination collision.'
mv -T -- "$WORK_DIR" "$FINAL_DIR"
trap - EXIT INT TERM
printf 'Backup complete: %s\nNo user files copied. No AWS actions or deletions.\n' "$FINAL_DIR"
