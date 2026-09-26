# Local operations

**English** | [Español](../es/operations.md)

The example timers use UTC. Set the intended time zone and staggered times for the target environment.

| Service | Check time |
|---|---|
| Nextcloud | 03:00 |
| Nginx Proxy Manager | 03:10 |
| Pi-hole | 03:20 |
| Plex | 03:30 |

Each check creates a backup only when 15 days have passed since the last complete set. For Plex, the first check of each month creates the monthly set, which also counts as that day's critical-state backup. `Persistent=true` catches up on a missed check after a VM restarts.

## Off-site upload

Each completed set is uploaded after its local checksum validation. The uploader sends only the files named in `manifest.json`, plus `manifest.json`, `SHA256SUMS`, and `COMPLETE`; it does not upload diagnostic logs. Before the next scheduled backup it verifies access to S3, so an unavailable bucket does not pause an application for a backup that cannot be transferred.

The credentials and bucket name stay on each VM, outside the repository:

```bash
sudo install -d -m 700 /etc/aws-homelab-dr
sudo install -m 600 /dev/null /etc/aws-homelab-dr/upload.env
sudoedit /etc/aws-homelab-dr/upload.env
```

Set only the following value in that file:

```text
AWS_HOMELAB_DR_BUCKET=replace-with-your-private-bucket
```

Configure the restricted uploader credentials as root with `sudo -H aws configure`, then run this read-only check before enabling automatic transfers:

```bash
sudo python3 /opt/aws-homelab-dr/scripts/lib/upload.py nextcloud --check
```

Use the local service name on each VM. The command checks the configuration and S3 access but does not upload or delete anything.

## Check the timers

```bash
systemctl list-timers 'homelab-backup-*' --all --no-pager
systemctl --failed --no-pager
```

To inspect a specific service:

```bash
sudo journalctl -u homelab-backup-plex.service -n 40 --no-pager
```

The oneshot service appears inactive when it is not running; its timer should be `enabled` and `active`.

## Pause a service

```bash
sudo systemctl disable --now homelab-backup-plex.timer
```

Replace `plex` with `nextcloud`, `npm`, or `pihole` as needed. This does not delete backups or stop a process that is already running.
