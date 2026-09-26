# Estrategia de respaldos

[English](../en/backup-strategy.md) | **Español**

El proyecto usa respaldos lógicos: configuración, bases de datos y estado de aplicaciones. No intenta copiar VMs completas ni el contenido pesado de los discos.

## Política local

| Conjunto | Frecuencia | Retención objetivo | Última medición |
|---|---|---:|---:|
| Nextcloud | 15 días | 6 | 3.9 MB |
| Nginx Proxy Manager | 15 días | 6 | 128 KB |
| Pi-hole | 15 días | 6 | 48 KB |
| Plex y auxiliares | 15 días | 6 | 14 MB |
| Plex metadata y media internos | Mensual | 6 | 341 MB |

Las mediciones se hicieron el 23 de septiembre de 2026 y están redondeadas. El mensual de Plex ya incluye el estado necesario para acompañar su metadata; no se debe sumar otra copia quincenal al calcular espacio.

Los timers de systemd revisan a diario en horario escalonado y ejecutan una copia solo cuando corresponde. Los conjuntos se generan bajo `/var/backups/homelab/`, se validan antes de marcarse como completos, se suben a S3 y se verifican de forma remota. Las reglas Lifecycle de S3 vencen conjuntos críticos tras 91 días y conjuntos mensuales de Plex tras 183 días.

## Qué se guarda

- **Nextcloud:** dump de MariaDB, configuración de Nextcloud, Apache, Samba, montajes e inventarios.
- **NPM:** base SQLite, claves de la aplicación, configuración nginx y compose.
- **Pi-hole:** configuración DNS y exportación de listas, reglas, grupos y clientes.
- **Plex:** bases, preferencias, respaldos nativos de Radarr, Sonarr, Prowlarr y Bazarr, más el estado de qBittorrent y servicios relacionados.
- **Plex mensual:** lo anterior más los directorios internos `Metadata/` y `Media/` de Plex.

Cada conjunto tiene manifiesto, hashes SHA-256 y un marcador `COMPLETE`. Eso comprueba que el archivo se creó y pasó sus verificaciones estructurales; no sustituye una restauración funcional.

## Exclusiones

No se incluyen los archivos de usuarios de Nextcloud, películas, series, descargas, imágenes de VM, cachés ni logs. Los certificados de Let's Encrypt de NPM se regenerarán al restaurar.

## Controles fuera de sitio

El bucket S3 acepta subidas únicamente mediante la identidad IAM limitada. Bloquea el acceso público, usa SSE-S3, rechaza transporte inseguro y mantiene la autoridad de borrado fuera de las VMs domésticas.
