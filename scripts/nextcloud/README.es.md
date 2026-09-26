# Nextcloud — respaldo local

[English](README.md) | **Español**

`backup.sh` genera el respaldo lógico de un host Nextcloud de referencia: dump MariaDB, configuración de Nextcloud, Apache, Samba, montajes e inventarios. Guarda las copias localmente y conserva las generaciones anteriores. Los archivos de Nextcloud quedan fuera del respaldo.

## Estado

Un timer activo revisa cada día si toca la siguiente copia quincenal. Los conjuntos completos se suben a S3 y las reglas Lifecycle administran su vencimiento.

## Ejecución en un host objetivo

Desde una copia revisada del repositorio en la VM:

```bash
sudo bash scripts/nextcloud/backup.sh --check
sudo bash scripts/nextcloud/backup.sh --run
```

Sin argumentos solo muestra ayuda. `--check` verifica requisitos sin crear respaldos ni cambiar mantenimiento; `--run` activa mantenimiento brevemente mientras captura DB/configuración. Ejecutarlo en una ventana sin otros respaldos, actualizaciones, jobs administrativos o escrituras externas por Samba. El bloqueo evita solapamiento entre instancias de este script, no con otros programas.

Rutas fijas según el inventario:

- Aplicación: `/var/www/nextcloud-app`, usuario `www-data`.
- MariaDB local: base `nextcloud`, acceso de root por socket, sin contraseñas en argumentos. No carga archivos de opciones del cliente.
- Configuración: `config/`, `/etc/apache2/sites-enabled/nextcloud.conf`, `/etc/fstab`, `/etc/samba/smb.conf`.
- Salida: `/var/backups/homelab/nextcloud/<UTC>-<identificador>/`.

Requiere Bash, PHP, Python 3, runuser, clientes MariaDB, tar/gzip, sha256sum, flock, dpkg-query y herramientas básicas de Ubuntu. Comprueba al menos 256 MiB libres como mínimo inicial; no es una garantía de espacio suficiente si crece la base. Aborta ante mantenimiento ya activo, actualización de DB pendiente o rutas/configuración inesperadas. Los enlaces simbólicos dentro de config/ requieren revisión manual; el enlace habitual de Apache se guarda con su contenido real.

## Archivos y comprobaciones

Cada conjunto completo contiene:

- `nextcloud-db.sql.gz`: dump con single-transaction, routines y triggers.
- `nextcloud-config.tar.gz`: configuración; **contiene secretos**.
- `nextcloud-status.json`, `nextcloud-apps.json` y `packages.txt`.
- `manifest.json`: tamaños y SHA-256 del contenido, alcance y restauración pendiente.
- `SHA256SUMS`: verifica contenido y manifiesto.
- `COMPLETE`: marcador de finalización, no de recuperación demostrada.
- `backup.log`: diagnóstico privado, excluido de Git.

Los directorios usan permisos 700 y los archivos se crean con umask 077. No mover estos resultados al repositorio ni publicar el log. Se comprueban gzip, tar, JSON, dump no vacío y SHA-256. Esto no demuestra que SQL pueda importarse ni que los archivos externos coincidan con la DB.

## Fallos y mantenimiento

Ante error o señal INT/TERM, intenta desactivar el mantenimiento que activó y conserva un directorio `.incomplete-*` para inspección; no lo cuenta como respaldo válido. Si no puede desactivar mantenimiento, devuelve error aunque el respaldo se haya generado. No borra respaldo anterior alguno.

SIGKILL, apagado del host o pérdida de energía no permiten ejecutar limpieza. Tras ese incidente revisar primero que no siga un respaldo/actualización activo; comprobar el estado y, cuando corresponda, salir de mantenimiento en la VM:

```bash
sudo -u www-data php /var/www/nextcloud-app/occ status
sudo -u www-data php /var/www/nextcloud-app/occ maintenance:mode --off
```

La configuración archivada se captura con mantenimiento activado. En la restauración final se deberá desactivarlo después de reponer DB/configuración y verificar coherencia con los datos externos. Los archivos de usuarios, temas personalizados y código de apps no se incluyen; las apps se inventarían para reinstalarlas en versiones compatibles. No es un respaldo completo de Nextcloud.

El modo de mantenimiento y el dump transaccional siguen el enfoque de la [documentación oficial de Nextcloud](https://docs.nextcloud.com/server/stable/admin_manual/maintenance/backup.html). El alcance reducido es una decisión de este proyecto.

Ver [política general](../../docs/es/backup-strategy.md) y [recuperación](../../docs/es/disaster-recovery.md).
