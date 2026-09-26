# Nginx Proxy Manager — local backup

**English** | [Español](README.es.md)

`backup.sh` uses the shared engine `../lib/backup.py` and requires Python 3.9 or later. Modes: `--help`, `--check`, and `--run`. A timer controls the biweekly schedule; completed sets are uploaded to S3 and S3 lifecycle rules handle expiration.

Requires Docker, the running `npm_app_1` container, `/root/npm/data` mounted at `/data`, SQLite at `data/database.sqlite`, `keys.json`, `data/nginx`, and `/root/npm/docker-compose.yml`.

`--run` briefly stops NPM, captures configuration and a SQLite snapshot through its API, checks integrity, and restarts the container. The proxy is unavailable during that interval. It keeps a minimal name/image/digest inventory without exporting container variables. Let's Encrypt certificates, logs, and Docker images are excluded.

Output goes to `/var/backups/homelab/npm/biweekly/<UTC>-<id>/`, with a manifest, SHA-256, and a COMPLETE marker. The first script backup used 128 KB. Unexpected symlinks cause an error and require review.

If capture or restart fails, it returns an error, keeps `.incomplete-*`, and attempts to restart NPM. Check the container manually after SIGKILL or shutdown. A complete set is published only after service recovery and file verification. Structural checks do not prove a functional restore.

See [local operations](../../docs/en/operations.md). Do not run with tracing or move outputs into the repository.
