# AWS Homelab DR

**English** | [Español](README.es.md)

A reference implementation for application-aware homelab backups with low-cost offsite storage in AWS S3.

## Current status

The reference workflow covers Nextcloud, Nginx Proxy Manager, Pi-hole, and Plex with its supporting applications. Each host uses a systemd timer that checks daily whether a backup is due; backups do not run every day.

| Service | Frequency | Latest measurement |
|---|---|---:|
| Nextcloud | Every 15 days | 3.9 MB |
| Nginx Proxy Manager | Every 15 days | 128 KB |
| Pi-hole | Every 15 days | 48 KB |
| Plex and supporting apps | Every 15 days | 14 MB |
| Plex metadata | Monthly | 341 MB |

These are example measurements from a small homelab. S3 lifecycle rules retain critical sets for 91 days and monthly Plex sets for 183 days.

## Scope

Backups cover configuration, databases, and state that would be difficult to rebuild. Nextcloud user files, movies, TV shows, and downloads are outside this project and need their own backup strategy.

The reference AWS design uses a private S3 Standard bucket, SSE-S3 encryption, blocked public access, restricted uploader credentials, and a small budget alert. Adjust resource names, retention, schedules, and cost limits to the environment.

## Documentation

- [Current architecture](docs/en/architecture.md)
- [Backup strategy](docs/en/backup-strategy.md)
- [Local operations](docs/en/operations.md)
- [Disaster recovery](docs/en/disaster-recovery.md)
- [Cost estimate](docs/en/cost-analysis.md)
- [Editable diagram](diagrams/as-is.mmd)

## Development

The backup scripts contain service-specific paths intended as templates. Review those paths before use. The scheduler uploads completed sets to S3 and validates remote object size and SHA-256 metadata. Deletion is handled by S3 lifecycle rules, not by the VMs. To run the synthetic checks:

```bash
python3 -m unittest discover -s tests -q
```
