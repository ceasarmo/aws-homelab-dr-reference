# Plex and supporting apps — local backup

**English** | [Español](README.es.md)

`backup.sh` uses `../lib/backup.py` (Python 3.9+). Local and monthly backups, plus automatic native ZIP generation for supporting apps, have completed successfully. An active timer controls the schedule; retention, uploads, and AWS resources are not implemented.

```bash
sudo bash scripts/plex/backup.sh --check
sudo bash scripts/plex/backup.sh --run
sudo bash scripts/plex/backup.sh --check --monthly
sudo bash scripts/plex/backup.sh --run --monthly
```

The biweekly set captures both Plex databases, Preferences.xml, fresh native ZIPs from the four supporting apps, qBittorrent configuration/state, Samba, fstab, and Bazarr/FlareSolverr units. Movies, TV shows, and downloads are excluded.

The monthly set captures **the same state plus internal Metadata/ and Media/**, with Plex stopped during capture. Each monthly set therefore has its own databases and configuration. The first monthly copy used 341 MB and the biweekly copy 14 MB. The internal Media folder contains Plex assets, not movies or TV shows.

Requires `Plex SQLite` at `/usr/lib/plexmediaserver/Plex SQLite`. Uses `.backup` and `PRAGMA integrity_check` with Plex's own tool, avoiding the tokenizer error from generic SQLite. Reference: [Plex SQLite tool](https://support.plex.tv/articles/repair-a-corrupted-database/).

Checks `plexmediaserver` and `qbittorrent-nox`. Only stops and restarts services that were active. Failed or transitional states require review. Both backup types share a lock to prevent overlap. Do not make external configuration or metadata changes during capture.

## Supporting application ZIPs

The engine requests new backups through local APIs and waits for results. It reads keys from local configuration without printing them. Manual ZIP generation is unnecessary, and old ZIPs are not accepted as substitutes. `--check` checks API access without requesting backups.

All four ZIPs are generated through local APIs and stored inside the private set. There is no need to create them from the web interfaces.

## Results and failures

Output is under `/var/backups/homelab/plex/biweekly/` or `monthly/`, with SHA-256, a manifest, and COMPLETE. IPC sockets are skipped; symlinks cause an error to avoid including unexpected external content.

The script attempts to restore both services after errors and INT/TERM signals. If a restart fails, a complete set is not published and manual recovery is needed. SIGKILL/shutdown prevent cleanup. Incomplete directories are kept; there is no automatic deletion.

Functional restore testing comes last. See [local operations](../../docs/en/operations.md).
