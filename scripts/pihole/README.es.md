# Pi-hole — respaldo lógico local

[English](README.md) | **Español**

`backup.sh` usa `../lib/backup.py` (Python 3.9+). Modos: `--help`, `--check`, `--run`. Un timer activo controla la cadencia quincenal. No detiene DNS ni crea recursos AWS.

Incluye `/etc/pihole/pihole.toml`, `dnsmasq.conf`, `hosts/custom.list` y exportación lógica de gravity.db. Usa una instantánea SQLite consistente en memoria para exportar adlist, domainlist, group, client y sus tres tablas de asociaciones. La ausencia de cualquiera de estas tablas provoca error para revisar el esquema real.

El JSON es un formato propio documentado con columnas y filas por tabla; **no es un archivo Teleporter ni puede importarse directamente como tal**. La restauración de estas tablas y sus relaciones debe implementarse y probarse en la fase final. No editar configuración/listas durante la captura: la transacción de SQLite no hace atómica la copia de los archivos externos.

No conserva historial DNS, cachés ni el contenido regenerable de listas gravity. La primera copia del script ocupó 48 KB.

Salida privada: `/var/backups/homelab/pihole/biweekly/<UTC>-<id>/`, con versión, configuración, rules.json, manifiesto, SHA-256 y COMPLETE. Los fallos quedan en `.incomplete-*`; no hay borrado de generaciones.

Consultar [operación local](../../docs/es/operations.md) y [configuración oficial Pi-hole](https://docs.pi-hole.net/ftldns/configfile/).
