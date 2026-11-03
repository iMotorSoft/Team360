# Team360 Operational Authority Policy

Esta política define quién autoriza una operación en Team360 y prohíbe que un agente introduzca trámites de aprobación por iniciativa propia.

## Propósito

Fijar quién autoriza una operación en Team360 y evitar que un agente invente jerarquías administrativas o bloqueos de aprobación. La seguridad técnica se conserva íntegra; la burocracia no aprobada se elimina.

## Regla central

La instrucción directa del responsable del proyecto autoriza la operación dentro de su alcance y de los permisos efectivos disponibles.

Ningún agente puede añadir políticas de aprobación, jerarquías administrativas ni bloqueos operativos nuevos sin una decisión explícita del responsable.

```text
instrucción del owner sobre un objetivo concreto = autoridad suficiente
```

Un agente que cree necesitar una confirmación nominal, una firma, un ticket, un campo `authorized_by` o una autorización privada adicional debe detenerse y preguntar antes de convertir esa necesidad en condición bloqueante.

## Lo que sigue siendo obligatorio

Las garantías técnicas no son burocracia y no se relajan por esta política.

Siguen siendo obligatorios CAS y compare-and-swap, validación de hashes y manifiestos, consistencia de componentes, locks de exclusión, journal durable, recuperación, rollback auditado, preflight de recursos y validación del reader canónico.

También se respetan los límites reales del entorno. Ser propietario del repositorio no concede permisos de infraestructura, credenciales, cuentas externas ni acceso a producción: cuando falta un permiso efectivo, el agente lo informa como límite técnico, no como aprobación pendiente.

## Trazabilidad automática

La trazabilidad se registra sola y no se convierte en un trámite adicional.

Journal, logs, hashes del plan, intención de commit, activación, verificación del reader y evidencia en `data/reports/` bastan para reconstruir qué se hizo, cuándo y sobre qué artefacto exacto.

Una identidad nominal o una referencia externa pueden registrarse si existen, pero son opcionales y nunca condicionan la operación. Los tests no otorgan autoridad operativa; el owner sí.

## Cómo distinguir un control legítimo de un trámite

Un control legítimo protege integridad, concurrencia, recuperación o un permiso externo real; su ausencia permite corromper datos o adjudicar acciones ajenas.

Un trámite es una ceremonia de aprobación que no cambia la garantía técnica y solo agrega pasos humanos. Ante la duda, el agente identifica quién introdujo el control y con qué decisión, describe qué garantía aporta y reporta el hallazgo. No debe exigir al owner que cumpla un requisito cuyo origen no puede justificar.

## Revisión y corrección

Un bloqueo administrativo sin decisión explícita se corrige quitando su carácter bloqueante, no pidiendo más confirmaciones.

La corrección conserva la auditoría automática y mantiene intactos los mecanismos de seguridad, integridad y recuperación. Después se completa la operación autorizada con el mecanismo canónico corregido.

El caso que originó esta política fue el requisito `authorized_by` en la promoción de Foundation de Telchi, incorporado por un agente como condición para publicar. Ver [promoción de ventas](../SrvRestAstroLS_v1/backend/modules/telchi/datalake/SALES_FOUNDATION_PROMOTION_V1.md) y [estado GLOBAL](../SrvRestAstroLS_v1/docs/status_actual.md).

## Alcance

Aplica a todos los agentes y frentes donde una operación pueda convertirse en un gate de aprobación.

Incluye Telchi/Data Lake, backend, frontend, deploys, migraciones, promociones y cualquier operación que un agente pudiera endurecer. Las políticas específicas conservan su detalle; ninguna puede endurecer esta regla sin decisión del responsable.
