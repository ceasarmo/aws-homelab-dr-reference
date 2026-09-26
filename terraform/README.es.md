# Terraform

[English](README.md) | **Español**

Esta carpeta define los primeros recursos para la copia externa:

- Un bucket privado S3 Standard en `us-east-1`.
- Cifrado SSE-S3 y bloqueo de acceso público.
- Un usuario IAM dedicado, limitado a los prefijos de respaldos.
- Sin permiso de borrar objetos para el usuario de subida.
- Expiración Lifecycle tras 91 días para conjuntos críticos y 183 días para metadata mensual de Plex.
- Versioning permanece desactivado para mantener simple el modelo inicial de almacenamiento.

Terraform no crea una access key. Se creará desde la consola de AWS después de aprobar el plan y se guardará directamente en cada VM. Nunca debe entrar a Git, al historial de la terminal ni a variables de Terraform.

## Antes de aplicar

Este módulo crea el bucket y la identidad limitada de subida en AWS.

1. Instalar Terraform e iniciar sesión en AWS con una cuenta administradora.
2. Copiar `terraform.tfvars.example` como `terraform.tfvars` y asignar un `bucket_name` globalmente único.
3. Ejecutar `terraform init` y `terraform plan`.
4. Revisar el plan: debe crear solamente los ajustes de seguridad del bucket, configuración Lifecycle, usuario IAM y política en línea. No debe crear un Budget, instancia EC2, recursos de red ni access keys.
5. Aplicar solamente después de revisar el plan.

Las reglas Lifecycle funcionan por antigüedad, por lo que conservan aproximadamente seis conjuntos cada 15 días y seis conjuntos mensuales de Plex; S3 puede eliminar un objeto poco después de que venza. Las VMs domésticas no reciben permiso para borrar objetos.

`.gitignore` excluye `terraform.tfvars`, archivos de estado, planes y credenciales. Después de ejecutar correctamente `terraform init`, versionar `.terraform.lock.hcl`.

Consultar [costos](../docs/es/cost-analysis.md) y [estrategia de respaldos](../docs/es/backup-strategy.md).
