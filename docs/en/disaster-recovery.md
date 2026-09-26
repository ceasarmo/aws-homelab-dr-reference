# Disaster recovery

**English** | [Español](../es/disaster-recovery.md)

## Status and limits

Initial backup sets completed local integrity checks and remote S3 upload verification. The recovery procedure below is designed for an isolated environment. Recovery time (RTO) is measured from the declared failure scenario until the service meets its acceptance criteria.

This project protects application configuration and state. If the Nextcloud file disks or media disks are lost without another copy, these backups cannot recover those files. Confirm the independent data copy before declaring a service recovered.

The target is to recover critical state no more than 15 days old and Plex metadata from the last month. Each test will measure data age (RPO) and the time needed to use the service again (RTO).

## Preparing a test

1. Choose a service and scenario: lost VM, corrupted configuration, or lost host.
2. Prepare an isolated machine/VM, enough space, and compatible versions; record application versions and the NPM image digest.
3. Access private backups, manifests, and credentials separately from Git. Keep credentials out of the report.
4. Record the start time, backup capture date, scope, and available external data.
5. Verify SHA-256 and files/databases before restoring. If checks fail, choose an earlier generation and record its age.
6. Avoid duplicate IPs, production DNS changes, and public exposure during the drill. Disable automatic downloads and tasks that modify real data.

If the physical host fails, restore compute, networking, and storage first. A local copy on the same host cannot cover that scenario; offsite backup is required for recovery from total loss.

## Suggested order

Restore connectivity and Pi-hole, rebuild Nextcloud and NPM, then the Plex stack. NPM can be prepared earlier, but its functional test needs Nextcloud available. Use temporary name resolution in an isolated drill to avoid circular DNS dependencies.

| Service | Restore to test | Acceptance criteria |
|---|---|---|
| Pi-hole | Install a compatible version, restore configuration, import rules/lists, and regenerate lists | External DNS resolves; the test hostname resolves to NPM; upstreams and blocking work; DHCP stays disabled |
| Nextcloud | Install compatible dependencies/apps, restore MariaDB and configuration, fix ownership, and mount the independent file copy | Healthy application status, successful login, and access to test files; verify database/file consistency and background jobs |
| NPM | Restore compose/configuration and SQLite snapshot; adjust targets for the test environment | SQLite integrity; restricted administration access; working Nextcloud proxy |
| Plex | Restore both databases and preferences with the service stopped, correct permissions, and test mounts | Integrity with Plex SQLite, successful startup, expected libraries/history, and playback of available test content |
| Plex supporting apps | Restore each app's native ZIP, qBittorrent configuration/state, Samba, and required units | Correct configuration and integrations, valid paths, download tasks stopped during the test |

NPM: since Let's Encrypt files are excluded, plan to issue new certificates and reconcile references to missing certificates in the database/configuration. Validate TLS before exposing the service. Use appropriate test mechanisms; missing files may need manual intervention.

Monthly Plex: restore `Metadata/` and `Media/` with the databases and configuration from the same set. Media libraries must be available separately.

Pi-hole also includes groups, clients, and associations in its logical export. Restoring that export still needs implementation and testing.

## Recording results and cleanup

Use the [report template](../../examples/restore-report.example.md). Record start/end times, infrastructure setup, backup retrieval, restore, functional validation, failures, and observed RPO. Measure RTO from the start of the declared scenario until functional criteria are met, noting exclusions.

Do not replace production during a drill. If it fails, retain sanitized evidence, stop the test environment, and leave the original service intact. A real migration needs a rollback point and prior data verification.

The first drill will run locally. Before an EC2 test, estimate instance, disk, IPv4, and transfer costs. Remove the environment afterward and check for leftover billable resources.
