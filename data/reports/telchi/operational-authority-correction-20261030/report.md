# Corrección de autoridad operativa y publicación de ventas

Auditoría del requisito `authorized_by` introducido en la promoción de Foundation de ventas, corrección del mecanismo y verificación de la publicación vigente.

## Hallazgo

El requisito no provino de una decisión del responsable del proyecto. Apareció en el wrapper nuevo `sales_foundation_promotion.py` y en su runbook, ambos todavía untracked, como condición bloqueante para publicar.

La secuencia observable en el worktree es:

1. El runbook `SALES_FOUNDATION_PROMOTION_V1.md` exigió identidad nominal real y referencia externa de autorización.
2. El reporte `sales-foundation-final-promotion-v1/operational-result.json` (30/10 07:38) declaró `BLOCKED` con `IDENTIFIED_AUTHORIZING_OWNER_MISSING`, aunque el owner ya había autorizado la operación en el mensaje.
3. Se generó el artefacto privado `authorization-request.json` y luego una autorización nominal separada para poder avanzar.
4. La promoción real se ejecutó a las 08:40 con `authorized_by` y `authorization_reference` tomados de un mensaje del owner, no de una política aprobada.

Ninguna instrucción del owner pidió ese trámite. El bloqueo fue una decisión de gobernanza tomada por un agente.

## Corrección aplicada

`Promotion.authorize` ya no exige identidad nominal ni referencia de autorización. Conserva el binding técnico exacto contra el plan preparado y rechaza cualquier valor provisto que no coincida.

- Se eliminó la condición bloqueante en `sales_foundation_promotion.py`.
- La traza opcional (`authorized_by`, `authorization_reference`, ticket) se archiva una vez y nunca bloquea ni reescribe un journal existente.
- El rollback dejó de exigir una autorización nominal previa; conserva el motivo auditado.
- La CLI `promote` funciona sin `--authorization`; el flag sigue disponible para quien quiera adjuntar traza.
- Se mantuvieron intactos CAS, hashes, locks, journal, recuperación, validación de manifiesto y verificación del reader.

Regla permanente: [team360-operational-authority-policy.md](../../../lat.md/team360-operational-authority-policy.md).

## Verificación

La regresión focalizada se ejecutó con `TMPDIR` en tmpfs porque el host tenía presión de I/O sostenida (`/proc/pressure/io` alrededor de 78 %) que hacía fallar el fixture de captura por presupuesto de persistencia, sin relación con el cambio.

- `pytest modules/telchi/datalake/tests` más los contratos comerciales de TelchiAI: 706 PASS en 79 s.
- Tests nuevos: publicación sin aprobación nominal, traza opcional idempotente y rollback sin traza registrada.
- Replay canónico del wrapper sobre el journal real, sin `--authorization`: `TECHNICALLY_ACTIVATED_READER_VERIFIED`, ocho componentes, `snapshot 1408`.
- Estado vivo confirmado por el store canónico: CURRENT `foundation_38680850adc058b1bb11887632b7b681`, Reference `v2_sales_e02883116f4b4991c396010a`.

## Límites

La transición de CURRENT ocurrió a las 08:40 con el mecanismo anterior. El replay corregido es idempotente y no volvió a publicar ni modificó datos. No se consultó SAP, no se recapturó, no se activó el scheduler y no se cambiaron permisos ni credenciales.
