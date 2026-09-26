# Operación local

[English](../en/operations.md) | **Español**

Los timers de ejemplo usan UTC. Configurar la zona horaria y horarios escalonados para el entorno objetivo.

| Servicio | Hora de revisión |
|---|---|
| Nextcloud | 03:00 |
| Nginx Proxy Manager | 03:10 |
| Pi-hole | 03:20 |
| Plex | 03:30 |

Cada revisión ejecuta el respaldo solo si pasaron 15 días desde el último conjunto completo. En Plex, la primera revisión de cada mes crea el conjunto mensual y también cuenta como el respaldo crítico de ese día. `Persistent=true` permite recuperar una revisión pendiente después de reiniciar una VM.

## Envío fuera de sitio

Cada conjunto completo se sube después de validar sus sumas de verificación locales. El cargador envía únicamente los archivos indicados por `manifest.json`, además de `manifest.json`, `SHA256SUMS` y `COMPLETE`; no sube los registros de diagnóstico. Antes del siguiente respaldo programado verifica el acceso a S3, para no pausar una aplicación si el conjunto no puede transferirse.

Las credenciales y el nombre del bucket quedan en cada VM, fuera del repositorio:

```bash
sudo install -d -m 700 /etc/aws-homelab-dr
sudo install -m 600 /dev/null /etc/aws-homelab-dr/upload.env
sudoedit /etc/aws-homelab-dr/upload.env
```

En ese archivo debe existir solamente este valor:

```text
AWS_HOMELAB_DR_BUCKET=replace-with-your-private-bucket
```

Configura las credenciales restringidas del cargador como root con `sudo -H aws configure`, y antes de habilitar transferencias automáticas ejecuta esta comprobación de solo lectura:

```bash
sudo python3 /opt/aws-homelab-dr/scripts/lib/upload.py nextcloud --check
```

Usa el nombre del servicio local de cada VM. El comando verifica la configuración y acceso a S3, pero no sube ni elimina nada.

## Comprobar los timers

```bash
systemctl list-timers 'homelab-backup-*' --all --no-pager
systemctl --failed --no-pager
```

Para revisar un servicio concreto:

```bash
sudo journalctl -u homelab-backup-plex.service -n 40 --no-pager
```

El servicio de ejecución puntual aparece inactivo cuando no está trabajando; el estado importante es que su timer esté `enabled` y `active`.

## Pausar un servicio

```bash
sudo systemctl disable --now homelab-backup-plex.timer
```

Sustituir `plex` por `nextcloud`, `npm` o `pihole` según corresponda. Esto no borra respaldos ni detiene un proceso que ya esté ejecutándose.
