# Plex y auxiliares — respaldo local

[English](README.md) | **Español**

`backup.sh` usa `../lib/backup.py` (Python 3.9+). Las copias local, mensual y la generación automática de ZIP de las aplicaciones auxiliares ya se completaron. Un timer activo controla la cadencia; no hay retención, subidas ni recursos AWS.

```bash
sudo bash scripts/plex/backup.sh --check
sudo bash scripts/plex/backup.sh --run
sudo bash scripts/plex/backup.sh --check --monthly
sudo bash scripts/plex/backup.sh --run --monthly
```

El quincenal captura ambas bases Plex, Preferences.xml, ZIP nativos recientes de las cuatro aplicaciones auxiliares, config/estado qBittorrent, Samba, fstab y unidades Bazarr/FlareSolverr. No copia películas, series ni descargas.

El mensual captura **ese mismo estado más Metadata/ y Media/ internos**, con Plex detenido durante la captura. Así, cada conjunto mensual conserva sus propias bases y configuración. La primera copia mensual ocupó 341 MB y la quincenal 14 MB. La carpeta interna Media contiene recursos de Plex, no las películas ni las series.

Requiere `Plex SQLite` en `/usr/lib/plexmediaserver/Plex SQLite`. Usa `.backup` y `PRAGMA integrity_check` con la herramienta propia de Plex, evitando el error de tokenizer del SQLite genérico. Referencia: [herramienta SQLite de Plex](https://support.plex.tv/articles/repair-a-corrupted-database/).

Confirma los servicios `plexmediaserver` y `qbittorrent-nox`. Solo detiene y reinicia los que estaban activos. Un estado fallido o transitorio requiere revisión. Los dos tipos de backup comparten bloqueo para no solaparse. No realizar cambios externos a configuración o metadatos durante la captura.

## ZIP de aplicaciones auxiliares

El motor solicita nuevos respaldos mediante las API locales y espera sus resultados. Lee claves de la configuración local sin imprimirlas. Ya no requiere generar ZIP manualmente ni acepta uno antiguo como sustituto. `--check` verifica acceso API sin solicitar respaldos.

Los cuatro ZIP se generan mediante las API locales y se guardan dentro del conjunto privado. No hace falta crearlos desde las interfaces web.

## Resultados y fallos

Salida en `/var/backups/homelab/plex/biweekly/` o `monthly/`, con SHA-256, manifiesto y COMPLETE. Los IPC sockets se omiten; los symlinks provocan error para evitar incluir contenido externo inesperado.

Se intenta restablecer ambos servicios tras errores y señales INT/TERM. Si un reinicio falla, no se publica un conjunto completo y se solicita recuperación manual. SIGKILL/apagado no permiten limpieza. Los directorios incompletos se conservan; no hay borrado automático.

La prueba funcional de restauración queda al final. Consultar [operación local](../../docs/es/operations.md).
