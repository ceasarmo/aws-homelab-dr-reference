# Nginx Proxy Manager — respaldo local

[English](README.md) | **Español**

`backup.sh` usa el motor común `../lib/backup.py` y requiere Python 3.9 o posterior. Modos: `--help`, `--check` y `--run`. Un timer controla la cadencia quincenal; los conjuntos completos se suben a S3 y las reglas Lifecycle manejan su vencimiento.

Requiere Docker, contenedor activo `npm_app_1`, montaje `/root/npm/data` hacia `/data`, SQLite en `data/database.sqlite`, `keys.json`, `data/nginx` y `/root/npm/docker-compose.yml`.

`--run` detiene NPM brevemente, captura configuración y snapshot SQLite mediante su API, verifica integridad y vuelve a iniciar el contenedor. Durante ese intervalo no estará disponible el proxy. Conserva un inventario mínimo de nombre/imagen/digest, sin exportar variables del contenedor. No incluye certificados Let's Encrypt, logs ni imágenes Docker.

La salida va a `/var/backups/homelab/npm/biweekly/<UTC>-<id>/`, con manifiesto, SHA-256 y marcador COMPLETE. La primera copia del script ocupó 128 KB. Rutas con enlaces simbólicos inesperados provocan error y requieren revisión.

Si fallan captura o reinicio, devuelve error y conserva `.incomplete-*`; intenta reiniciar NPM. Ante SIGKILL/apagado revisar manualmente el contenedor. Una copia completa solo se publica después de recuperar el servicio y verificar archivos. Una verificación estructural no demuestra restauración funcional.

Consultar la [operación local](../../docs/es/operations.md). No ejecutar con trazas ni mover resultados al repositorio.
