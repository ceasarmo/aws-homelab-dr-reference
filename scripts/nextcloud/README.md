# Nextcloud — local backup

**English** | [Español](README.es.md)

`backup.sh` creates a logical backup of a reference Nextcloud host: MariaDB dump, Nextcloud, Apache and Samba configuration, mounts, and inventories. It stores copies locally and keeps earlier generations. Nextcloud files are outside the backup scope.

## Status

An active timer checks daily whether the next biweekly copy is due. Completed sets are uploaded to S3 and lifecycle rules manage expiration.

## Running on a target host

From a reviewed copy of the repository on the VM:

```bash
sudo bash scripts/nextcloud/backup.sh --check
sudo bash scripts/nextcloud/backup.sh --run
```

Without arguments, it only shows help. `--check` checks prerequisites without creating backups or changing maintenance mode; `--run` briefly enables maintenance mode while capturing the database/configuration. Run it without concurrent backups, updates, administrative jobs, or external Samba writes. The lock prevents overlap between instances of this script, not other programs.

Fixed paths from the inventory:

- Application: `/var/www/nextcloud-app`, account `www-data`.
- Local MariaDB: database `nextcloud`, root access through a socket, no passwords in arguments. Client option files are not loaded.
- Configuration: `config/`, `/etc/apache2/sites-enabled/nextcloud.conf`, `/etc/fstab`, `/etc/samba/smb.conf`.
- Output: `/var/backups/homelab/nextcloud/<UTC>-<identifier>/`.

Requires Bash, PHP, Python 3, runuser, MariaDB clients, tar/gzip, sha256sum, flock, dpkg-query, and basic Ubuntu tools. Checks for at least 256 MiB free as an initial minimum; this does not guarantee enough space if the database grows. Aborts if maintenance is already active, a database upgrade is pending, or paths/configuration are unexpected. Symlinks inside config/ need manual review; the usual Apache symlink is saved as its actual content.

## Files and checks

Each complete set contains:

- `nextcloud-db.sql.gz`: dump with single-transaction, routines, and triggers.
- `nextcloud-config.tar.gz`: configuration; **contains secrets**.
- `nextcloud-status.json`, `nextcloud-apps.json`, and `packages.txt`.
- `manifest.json`: content sizes and SHA-256, scope, and pending restore status.
- `SHA256SUMS`: checks content and manifest.
- `COMPLETE`: completion marker, not proof of recovery.
- `backup.log`: private diagnostics, excluded from Git.

Directories use permissions 700 and files are created with umask 077. Keep these outputs outside the repository and do not publish the log. Checks cover gzip, tar, JSON, a nonempty dump, and SHA-256. They do not prove SQL can be imported or external files match the database.

## Failures and maintenance

On error or INT/TERM, the script tries to disable the maintenance mode it enabled and keeps an `.incomplete-*` directory for inspection; it is not counted as a valid backup. If maintenance cannot be disabled, it returns an error even if the backup was created. Earlier backups are not deleted.

SIGKILL, host shutdown, or power loss prevent cleanup. After such an incident, first check that no backup/update is still running; inspect status and, when appropriate, leave maintenance mode on the VM:

```bash
sudo -u www-data php /var/www/nextcloud-app/occ status
sudo -u www-data php /var/www/nextcloud-app/occ maintenance:mode --off
```

The archived configuration is captured with maintenance enabled. During recovery, disable it after restoring the database/configuration and verifying consistency with external data. User files, custom themes, and app code are excluded; apps are inventoried for reinstallation at compatible versions. This is not a full Nextcloud backup.

Maintenance mode and the transactional dump follow the [official Nextcloud documentation](https://docs.nextcloud.com/server/stable/admin_manual/maintenance/backup.html). The reduced scope is a project choice.

See the [general policy](../../docs/en/backup-strategy.md) and [recovery](../../docs/en/disaster-recovery.md).
