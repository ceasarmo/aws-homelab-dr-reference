# Backup strategy

**English** | [Español](../es/backup-strategy.md)

The project uses logical backups: configuration, databases, and application state. It does not copy entire VMs or large data volumes.

## Local policy

| Backup set | Frequency | Target retention | Latest measurement |
|---|---|---:|---:|
| Nextcloud | 15 days | 6 | 3.9 MB |
| Nginx Proxy Manager | 15 days | 6 | 128 KB |
| Pi-hole | 15 days | 6 | 48 KB |
| Plex and supporting apps | 15 days | 6 | 14 MB |
| Plex internal metadata and media | Monthly | 6 | 341 MB |

Measurements were taken on September 23, 2026 and are rounded. The monthly Plex set already includes the state needed alongside its metadata; do not add another biweekly copy when estimating space.

The systemd timers check daily at staggered times and create a backup only when due. Sets are created under `/var/backups/homelab/`, validated before being marked complete, uploaded to S3, and verified remotely. S3 lifecycle rules expire critical sets after 91 days and Plex monthly sets after 183 days.

## Contents

- **Nextcloud:** MariaDB dump, Nextcloud, Apache and Samba configuration, mounts, and inventories.
- **NPM:** SQLite database, application keys, nginx configuration, and compose file.
- **Pi-hole:** DNS configuration and exports of lists, rules, groups, and clients.
- **Plex:** databases, preferences, native Radarr, Sonarr, Prowlarr and Bazarr backups, plus qBittorrent state and related services.
- **Monthly Plex:** all of the above plus Plex's internal `Metadata/` and `Media/` directories.

Each set includes a manifest, SHA-256 hashes, and a `COMPLETE` marker. This means the files were created and passed structural checks; it does not replace a functional restore.

## Exclusions

Nextcloud user files, movies, TV shows, downloads, VM images, caches, and logs are excluded. NPM's Let's Encrypt certificates will be regenerated during recovery.

## Offsite controls

The S3 bucket accepts uploads only through the limited IAM identity. It blocks public access, uses SSE-S3, denies insecure transport, and keeps deletion authority outside the home VMs.
