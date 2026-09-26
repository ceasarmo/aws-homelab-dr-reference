# AWS Homelab DR

[English](README.md) | **Español**

Implementación de referencia para respaldos de aplicaciones en un homelab con almacenamiento externo económico en AWS S3.

## Estado actual

El flujo de referencia cubre Nextcloud, Nginx Proxy Manager, Pi-hole y Plex con sus aplicaciones auxiliares. Cada host usa un timer de systemd que revisa diariamente si toca crear una copia; no ejecuta un respaldo diario.

| Servicio | Frecuencia | Última medición |
|---|---|---:|
| Nextcloud | Cada 15 días | 3.9 MB |
| Nginx Proxy Manager | Cada 15 días | 128 KB |
| Pi-hole | Cada 15 días | 48 KB |
| Plex y auxiliares | Cada 15 días | 14 MB |
| Plex metadata | Mensual | 341 MB |

Los resultados son mediciones de ejemplo de un homelab pequeño. Las reglas Lifecycle conservan conjuntos críticos durante 91 días y conjuntos mensuales de Plex durante 183 días.

## Alcance

Se respaldan configuraciones, bases de datos y estado difícil de reconstruir. Los archivos de usuarios de Nextcloud, películas, series y descargas se mantienen fuera de este proyecto y requieren su propia estrategia de protección.

El diseño de referencia en AWS usa un bucket privado S3 Standard, cifrado SSE-S3, acceso público bloqueado, credenciales de subida restringidas y una alarma de presupuesto pequeña. Ajustar nombres de recursos, retención, horarios y límites de costo al entorno.

## Documentación

- [Arquitectura actual](docs/es/architecture.md)
- [Estrategia de respaldos](docs/es/backup-strategy.md)
- [Operación local](docs/es/operations.md)
- [Recuperación ante desastres](docs/es/disaster-recovery.md)
- [Estimación de costos](docs/es/cost-analysis.md)
- [Diagrama editable](diagrams/as-is.es.mmd)

## Desarrollo

Los scripts contienen rutas específicas de servicios y deben revisarse antes de usarse. El scheduler sube los conjuntos completos a S3 y valida tamaño y metadatos SHA-256 remotos. La eliminación la gestionan reglas Lifecycle de S3, no las VMs. Para ejecutar las comprobaciones sintéticas:

```bash
python3 -m unittest discover -s tests -q
```
