# Pi-hole — local logical backup

**English** | [Español](README.es.md)

`backup.sh` uses `../lib/backup.py` (Python 3.9+). Modes: `--help`, `--check`, `--run`. An active timer controls the biweekly schedule. It does not stop DNS or create AWS resources.

Includes `/etc/pihole/pihole.toml`, `dnsmasq.conf`, `hosts/custom.list`, and a logical export of gravity.db. A consistent in-memory SQLite snapshot exports adlist, domainlist, group, client, and their three association tables. Missing any of these tables causes an error so the actual schema can be reviewed.

The JSON is a custom format with columns and rows per table; **it is not a Teleporter file and cannot be imported directly as one**. Restoring these tables and relationships needs implementation and testing in the final phase. Do not edit configuration/lists during capture: the SQLite transaction does not make external file copying atomic.

DNS history, caches, and regenerable gravity list contents are excluded. The first script backup used 48 KB.

Private output: `/var/backups/homelab/pihole/biweekly/<UTC>-<id>/`, with version, configuration, rules.json, manifest, SHA-256, and COMPLETE. Failed runs stay in `.incomplete-*`; generations are not deleted.

See [local operations](../../docs/en/operations.md) and [official Pi-hole configuration](https://docs.pi-hole.net/ftldns/configfile/).
