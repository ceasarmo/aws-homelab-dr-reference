#!/usr/bin/env bash
# Installs units only. Activation is a separate visible step.
set -Eeuo pipefail
[[ $# == 1 ]] || { echo 'Usage: sudo bash scripts/schedule/install.sh nextcloud|npm|pihole|plex' >&2; exit 2; }
case "$1" in nextcloud|npm|pihole|plex) SERVICE=$1 ;; *) exit 2 ;; esac
[[ $EUID == 0 && $(uname -s) == Linux ]] || { echo 'Run with sudo on the Ubuntu VM.' >&2; exit 1; }
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
UNIT=homelab-backup-$SERVICE
[[ -f "$SOURCE/systemd/$UNIT.service" && -f "$SOURCE/systemd/$UNIT.timer" ]]
[[ -f /opt/aws-homelab-dr/scripts/$SERVICE/backup.sh ]]
[[ -f /opt/aws-homelab-dr/scripts/schedule/run.py ]]
# Verify syntax/calendar support on the actual systemd version before installation.
systemd-analyze verify "$SOURCE/systemd/$UNIT.service" "$SOURCE/systemd/$UNIT.timer"
CALENDAR=$(sed -n 's/^OnCalendar=//p' "$SOURCE/systemd/$UNIT.timer")
systemd-analyze calendar "$CALENDAR"
install -o root -g root -m 644 "$SOURCE/systemd/$UNIT.service" "/etc/systemd/system/$UNIT.service"
install -o root -g root -m 644 "$SOURCE/systemd/$UNIT.timer" "/etc/systemd/system/$UNIT.timer"
systemctl daemon-reload
printf 'Units installed; no timer enabled by this installer. Check status before enabling.\n'
