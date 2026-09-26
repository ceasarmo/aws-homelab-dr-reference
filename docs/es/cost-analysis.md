# Costos

[English](../en/cost-analysis.md) | **Español**

La meta es gastar **menos de US$0.10 al mes** durante la operación normal. El presupuesto de AWS está configurado en **US$2 al mes** para detectar desvíos, aunque un presupuesto es una alerta y no un límite que detenga cargos.

## Estimación inicial

Con seis generaciones por categoría y las medidas actuales, la retención local equivalente es de aproximadamente **2.15 GB**. Como referencia de planificación, S3 Standard en `us-east-1` costaba US$0.023 por GB-mes al elaborar este proyecto:

```text
2.15 GB × US$0.023 ≈ US$0.05 al mes
```

La cifra no incluye solicitudes, restauraciones, transferencias, impuestos ni crecimiento. Antes de crear el bucket hay que confirmar tarifas y medir bytes reales. [Precios de S3](https://aws.amazon.com/s3/pricing/).

## Decisiones para mantenerlo pequeño

| Área | Decisión inicial |
|---|---|
| Almacenamiento | Un bucket privado S3 Standard |
| Cifrado | SSE-S3 |
| Retención | Seis conjuntos por categoría |
| Cómputo | Sin EC2 permanente |
| Red | Sin NAT Gateway, ALB, endpoints ni dominio nuevo |
| Servicios gestionados | Sin RDS, ECS ni Fargate |
| Versioning, Object Lock y KMS propia | Fuera de la primera versión |

Las pruebas futuras en la nube se estimarán por separado y se eliminarán al terminar. La primera restauración se hará localmente.
