# Recuperación ante desastres

[English](../en/disaster-recovery.md) | **Español**

## Estado y límites

Los conjuntos iniciales completaron las comprobaciones de integridad local y la verificación de subida remota a S3. El procedimiento de recuperación siguiente está diseñado para un entorno aislado. El tiempo de recuperación (RTO) se mide desde el escenario de fallo declarado hasta que el servicio cumple sus criterios de aceptación.

Este proyecto protege configuración y estado de aplicaciones. Si se pierden los discos de archivos Nextcloud o de contenido multimedia y no existe otra copia, estos respaldos no recuperan esos archivos. Confirmar la copia independiente de datos antes de declarar recuperado un servicio.

El objetivo es recuperar estado crítico con un máximo de 15 días de antigüedad y metadatos Plex del último mes. En cada prueba se medirá la antigüedad de los datos (RPO) y el tiempo necesario para volver a usar el servicio (RTO).

## Preparación de una prueba

1. Seleccionar servicio y escenario: pérdida de VM, corrupción de configuración o pérdida del host.
2. Disponer de equipo/VM aislada, espacio suficiente y versiones compatibles; registrar versiones de aplicaciones y digest de la imagen NPM.
3. Acceder a respaldos privados, manifiestos y credenciales por un canal independiente de Git. No volcar credenciales en el informe.
4. Anotar hora de inicio, fecha de captura del respaldo, alcance y datos externos disponibles.
5. Verificar SHA-256 y archivos/DB antes de restaurar. Si fallan, elegir una generación anterior y registrar su antigüedad.
6. Evitar IPs duplicadas, cambios de DNS de producción y exposición pública durante el ensayo. Desactivar descargas automáticas y tareas que alteren datos reales.

Si falla el host físico completo, primero restablecer cómputo, red y almacenamiento. La copia local en el mismo host no resuelve ese escenario; la copia externa futura es una dependencia del DR ante pérdida total.

## Secuencia sugerida

Recuperar conectividad y Pi-hole, reconstruir Nextcloud y NPM, y por último el stack Plex. NPM puede prepararse antes, pero su prueba funcional requiere que Nextcloud ya esté disponible. En un ensayo aislado usar resolución temporal para evitar un bloqueo circular de DNS.

| Servicio | Restauración que debe ensayarse | Criterios de aceptación |
|---|---|---|
| Pi-hole | Instalar versión compatible, restaurar configuración, importar listas/reglas y regenerar listas | Resuelve DNS externo; el hostname de prueba resuelve a NPM; upstreams y bloqueo funcionan; DHCP permanece desactivado |
| Nextcloud | Instalar dependencias/apps compatibles, restaurar MariaDB y configuración, corregir propietarios y montar copia externa de archivos | Estado de aplicación sano, login correcto y acceso a archivos de prueba; comprobar coherencia DB/archivos y jobs de fondo |
| NPM | Reponer compose/configuración y snapshot SQLite; ajustar destinos al entorno de prueba | Integridad SQLite; administración accesible solo donde corresponde; proxy a Nextcloud funcional |
| Plex | Restaurar ambas bases y preferencias con el servicio detenido, permisos correctos y montajes de prueba | Integridad con Plex SQLite, inicio correcto, bibliotecas/historial esperados y reproducción de contenido de prueba disponible |
| Auxiliares Plex | Restaurar ZIP nativo de cada aplicación; config/estado qBittorrent; Samba y unidades necesarias | Configuración e integraciones correctas, rutas válidas, tareas de descarga detenidas durante la prueba |

NPM: al excluir Let's Encrypt, prever emisión de certificados nuevos y reconciliar referencias a certificados ausentes en su base/configuración. No publicar el servicio hasta validar TLS. En pruebas usar mecanismos de prueba adecuados; no asumir que los archivos faltantes se regeneran sin intervención.

Plex mensual: restaurar `Metadata/` y `Media/` con las bases y configuración del mismo conjunto. Las bibliotecas multimedia deben estar disponibles por separado.

Pi-hole conserva también grupos, clientes y asociaciones en su exportación lógica. La restauración de esa exportación sigue pendiente de ser implementada y probada.

## Registro y cierre

Usar [la plantilla de informe](../../examples/restore-report.example.es.md). Registrar inicio/fin, preparación de infraestructura, obtención de respaldos, restauración, validación funcional, fallos y RPO observado. Medir el RTO desde el inicio del escenario declarado hasta cumplir los criterios funcionales, especificando exclusiones.

No reemplazar producción durante un ensayo. Si falla, conservar evidencia sanitizada, detener el entorno de prueba y mantener intacto el servicio original. Una migración real requiere un punto de retorno y verificación previa de los datos.

El primer ensayo será local. Para una prueba en EC2 habrá que calcular antes el costo de instancia, disco, IPv4 y transferencias. Al terminar, eliminar el entorno y comprobar que no queden recursos cobrables.
