# Promoción del runtime comercial TelchiAI DEV — 10/11/2026

Cierre operativo de la implementación D1–D5: corrección semántica de la
diferencia absoluta, consolidación Git, publicación en GitHub, reacreditación
canónica de los seis gates y recarga controlada de WhatsApp DEV.

Frente: `feature/console-backend-core`.
Cierre: `2026-11-10T22:20Z` (UTC).

| Artefacto | Contenido |
| --- | --- |
| `report.md` | Este informe |
| `report.json` | Los mismos hechos en forma estructurada |
| `reaccredit.py` | Wrapper de ventana sobre el runner canónico: reutiliza sondas y publicador sin cambios y aísla sólo el subproceso pytest |

---

## 1. Estados finales

| Estado | Resultado |
| --- | --- |
| `ABSOLUTE_DIFFERENCE_SEMANTICS` | PASS |
| `COMMERCIAL_CAPABILITY_CLOSURE` | PASS |
| `COMPOSITE_RESULT_CONTINUITY` | PARTIAL (contrato de referencias cubierto por pruebas; diferencia sobre una celda compuesta que mezcla escalas sigue requiriendo su propia ventana) |
| `FREE_INVESTIGATION_PRESERVED` | PASS |
| `FAST_PATH_PRESERVED` | PASS |
| `SECURITY` | PASS |
| `GIT_CONSOLIDATION` | PASS |
| `GITHUB_PUSH` | PASS |
| `SIX_GATES` | PASS |
| `WHATSAPP_DEV_RELOAD` | PASS |
| `ACTIVE_CODE_MATCH` | PASS |
| `READY_FOR_DIALOGUE` | YES |
| `EXTERNAL_WHATSAPP_E2E` | NOT_TESTED |

No se confunde código publicado con código activo: ambos se verificaron por
separado (secciones 5 y 8).

## 2. Git

| Hecho | Valor |
| --- | --- |
| Rama | `feature/console-backend-core` |
| HEAD anterior | `2ff367fa9a78979cecd371f2afe7b7bba5b65990` |
| HEAD consolidado | `dbc86d9c8093c48e92504ea4df12f733c41a9d24` |
| Remoto | `origin` = `dbc86d9c8093c48e92504ea4df12f733c41a9d24` (idéntico) |
| Push | normal, sin `--force` |
| Alcance | 33 archivos, `+2953 / −132` |
| `git diff --check` | sin hallazgos |
| `lat check` | All checks passed |

### Archivos modificados

`business_semantics/`: `resolver.py`, `tests/test_embedded_meanings.py`.
`telchi/assistant/`: `README.md`, `capabilities.py`, `canonical_runtime_probe.py`,
`composition.py`, `handler.py`, `luna.py`, `monetary_comparison.py`,
`repository.py`, `result_references.py`, `whatsapp_dev.py`,
`whatsapp_dev_lifecycle.py`, `tests/{test_absolute_difference_semantics,
test_business_categories, test_canonical_knowledge, test_commercial_scope_closure,
test_composite_continuity, test_ranking_contract_admission, test_sales_monetary}.py`.
`telchi/datalake/`: `sales_query.py`.
`telchi/exploratory_sql/`: `adaptive_research.py`, `ask.py`, `ask_verifier.py`,
`authorized_foundation.py`, `console_bridge.py`, `test_authorized_foundation.py`,
`test_business_knowledge_binding.py`, `test_dynamic_verification_budget.py`,
`test_observation_budget.py`, `test_quantitative_semantics.py`.
`telchi/`: `research_port.py`, `test_research_port.py`.

### Excluido del commit y preservado local

- Evidencia empresarial bajo `data/reports/` (116 directorios/archivos sin
  seguimiento, con importes reales y artefactos de ejecución).
- Configuración privada (`PRIVATE_ROOT`), bases de datos, dumps SAP y
  credenciales: nunca estuvieron dentro del árbol versionado.
- Respaldo recuperable previo al commit:
  `ai/private/team360-git-backup-20261110T220522Z/` (`head.txt`,
  `tracked-unstaged.patch`, `new-source-files.tgz`, `status.txt`).

Ningún archivo excluido fue borrado. Los cambios concurrentes de ambos agentes
se preservaron y se publicaron juntos.

## 3. Diferencia absoluta — causa y corrección

Pregunta real del seguimiento: «¿Cuál fue la diferencia absoluta entre esos dos
meses?». El sistema respondió con la operación `CALCULATE` y un importe
negativo (`BS -28.024,28`).

Causa real: el contrato local de comparación (`MONETARY_COMPARISON`) sólo
admitía `difference` (resta con signo) y `percent` (variación). No existía un
modo de diferencia absoluta en ese contrato —aunque el contrato de referencias
de resultado sí distingue `subtract` de `absolute_difference`—. La pregunta por
una magnitud se respondió con la resta con signo, sin separar magnitud de
dirección. No era un error de cálculo ni un problema de datos.

Corrección (sin tocar importes históricos):

- Nuevo modo `absolute_difference` en comparación de períodos y de componentes,
  junto a `difference`, `percent` y `ratio_percent`.
- La auditoría conserva simultáneamente `difference` (con signo),
  `absolute_difference` (magnitud), `direction`
  (`target_higher`/`baseline_higher`/`equal`), `reported`
  (`signed`/`absolute`) y `value` (la cifra entregada).
- El texto declara magnitud y dirección por separado; una diferencia absoluta
  no se responde con un importe negativo.
- La guía del intérprete elige el modo por lo que pide la pregunta y prohíbe
  confundir participación con variación y diferencia con signo con diferencia
  absoluta.
- Un modo desconocido se rechaza (`ambiguous_comparison`) en lugar de degradar
  silenciosamente a resta con signo.

## 4. Pruebas focalizadas

| Comando | Resultado |
| --- | --- |
| `uv run pytest modules/telchi/assistant/tests/test_absolute_difference_semantics.py -q` | `10 passed` |
| `uv run pytest modules/telchi/assistant -q` | `1128 passed, 4 skipped` |
| `uv run pytest modules/telchi/exploratory_sql modules/telchi/test_research_port.py -q` | `429 passed` |
| `uv run pytest` (5 archivos `datalake` del informe D1–D5) | `20 passed, 1 skipped` |
| `uv run pytest modules/business_semantics/tests/test_embedded_meanings.py -q` | `2 passed` |
| Gate de reacreditación (suite completa del runner) | `1246 passed, 4 skipped` |
| `git diff --check` | sin salida |
| `lat check` | All checks passed |

Regresiones de la corrección semántica (`test_absolute_difference_semantics.py`):
A mayor que B, A menor que B, A igual a B, diferencia absoluta, diferencia con
signo, variación porcentual, participación de componentes, modo desconocido
rechazado, precisión `Decimal` con moneda `BS`, y seguimiento real sobre los dos
operandos persistidos.

D1–D5, continuidad de operandos, capabilities rápidas, investigación libre,
presupuesto de observaciones y autorización empresarial siguen cubiertos por sus
suites y por las seis garantías reejecutadas.

No se modificó comportamiento para obtener PASS; la suite del gate se ejecutó con
el mismo aislamiento de fixtures ya documentado en ventanas previas (sección 6).

## 5. Gates — reacreditación canónica

Mecanismo: `data/reports/telchi/six-gates-reaccreditation-20261021/reaccredit.py`
(ejecutado a través de `reaccredit.py` de este directorio, que reutiliza sondas y
publicador sin cambios). No se editaron manifiestos ni hashes a mano.

| Hecho | Valor |
| --- | --- |
| Política | `change_based_v1`, `schema_version` 2, sin `expires_at` |
| `source_sha256` | `3b84888dbc9d39253f143c8829db51e183a91b729caa45557b8f222888bc8bf5` |
| `configuration_sha256` | `78fd5d12b6076f3f0e7551ec8fb47c5ed17a63678ed04fd0602d2536e1028ea5` |
| `approval_sha256` | `f548d798c479d976e532098eaac170864ca30024b53769bec93dd5b9349cf8c5` |
| Manifiesto publicado | `bb55d8adac8040955e27cbbd62c3a8b09fa424c347a89f68f5c76bfc47792de5` |
| Artefacto final | `six-gates-20261110T221243545383Z/final-accreditation.json` (`90b9034c…`) |

Seis garantías, todas `PASS` / `kind=real`, con artefacto privado y hash exacto:

| Gate | Estado |
| --- | --- |
| `http_auth` | PASS |
| `identity_tenant_isolation` | PASS |
| `business_authorization` | PASS |
| `durable_idempotency` | PASS |
| `assistant_foundation` | PASS |
| `model_no_fallback` | PASS |

`synthesis`: `SIX_GATES=VALID`, `CURRENT_CODE_FINGERPRINT=VALID`,
`CURRENT_PILOT_CONTRACT=VALID`, `REAL_SECURITY_BOUNDARIES=PASS`,
`READY_FOR_MANUAL_START=YES`.

### Intentos bloqueados, conservados

1. Primer intento: `OSError` por el puerto `18181` ocupado por la sesión DEV que
   seguía viva (el estado se mostraba como `STOPPED` porque el campo sólo cambia
   a `RUNNING`; el estado real era `DEGRADED` por gates vencidos). No se publicó
   manifiesto. Resuelto con la parada canónica, no matando procesos ajenos.
2. Segundo intento: las seis garantías reales PASS, pero el subproceso de tests
   falló con `18 failed` porque heredó la configuración operativa privada
   (`TEAM360_*`/`META_TEAM360_*`) dentro de fixtures unitarias —el modo de fallo
   ya documentado en la ventana anterior—. Manifiesto no publicado.
3. Tercer intento con aislamiento de fixtures (`original_environment` y umask
   `0o022` sólo para el subproceso offline): `1246 passed, 4 skipped` y
   manifiesto publicado.

No se relajó ninguna garantía para desbloquear; en los intentos 1 y 2 el
publicador quedó en `manifest_changed=false`.

## 6. Procedimiento de recarga

Mecanismo canónico, desde `/media/issajar/DEVELOP/Projects/iMotorSoft/ai/dev/Team360`:

```bash
./whatsapp-dev.sh down     # parada de la sesión propia
./whatsapp-dev.sh status
# reacreditación en sesión inerte (down → reaccredit → up)
uv run python ../../data/reports/telchi/commercial-runtime-promotion-20261110/reaccredit.py
./whatsapp-dev.sh up
./whatsapp-dev.sh status
```

Por qué esta ventana: la reacreditación exige sesión inerte
(`exclusive_inert_reaccreditation_required`) y el arranque exige gates válidos
(`gate_evidence`), así que parada, reacreditación y arranque son una sola
operación. Es el mismo mecanismo documentado en ventanas previas; no existe una
recarga en caliente canónica más segura.

Precondiciones verificadas antes de `down`:

- Estado real `DEGRADED` con `launcher=OWNED`, `backend=OWNED`,
  `webhook=SESSION`, `evolution=READY`, `postgresql=READY`, `durable_worker=PASS`;
  causa de degradación: gates vencidos por cambio de código.
- Trabajo durable pendiente: `0` no terminal; outbox no terminal: `0` (sólo
  `FAILED_FINAL` y `OUTBOUND_ACCEPTED` históricos, ambos terminales).
- Servicios compartidos: `POSTGRES=READY`, `LITELLM=READY`, `EVOLUTION=READY`,
  `CLOUDFLARE=READY`, `META_CALLBACK=SYNCED`.

Parada: `state=STOPPED`, `webhook=INTERNAL`, puerto `18181` libre, Evolution y
PostgreSQL intactos. No se detuvo PostgreSQL, LiteLLM, Evolution ni Cloudflare;
no se modificó Meta ni el túnel.

## 7. Estado final de servicios

```text
POSTGRES=READY
LITELLM=READY
EVOLUTION=READY
CLOUDFLARE=READY
META_CALLBACK=SYNCED
SIX_GATES=PASS
WHATSAPP_RUNTIME=RUNNING
READY_FOR_DIALOGUE=YES
BLOCKER=NONE
```

## 8. Identidad del código activo

No se infiere sólo de `RUNNING`:

| Comprobación | Evidencia |
| --- | --- |
| Árbol de trabajo | sin cambios sin commit en `SrvRestAstroLS_v1/backend` (HEAD = código en disco) |
| HEAD vs remoto | `dbc86d9…` en ambos |
| `source_digest()` en vivo | `3b84888d…` = `source_sha256` del manifiesto publicado |
| `configuration_digest()` / `approval_digest()` | coinciden con el manifiesto |
| Arranque vs cambios | backend `started 19:14:44 -0300` (22:14:44Z), posterior al archivo de fuente más reciente (22:01:03Z) |
| Sesión | nueva `15bb5afca9ee3066bef3760d97599ec6`, launcher y backend `OWNED` |
| Startup | `backend.log` vacío, `backend-diagnostics.json` = `{"original_error": null, "stage": "backend_listening"}` |
| Worker / persistencia | `durable_worker=PASS`, `postgresql=READY` |
| Outbox | `in_flight=0`; sin intents no terminales |

El marcador de actividad registró un evento de webhook al arrancar (`turns=1`,
`in_flight=0`) sin fila de mensaje en `message_events` para la ventana: fue un
evento de estado de Evolution al reapuntar el webhook de la sesión, no una
conversación. No se procesó ningún mensaje entrante ni se emitió un envío.

## 9. Resultado del push

`2ff367f..dbc86d9  feature/console-backend-core -> feature/console-backend-core`,
exit 0; tras `fetch`, HEAD local y `origin` idénticos. Sin `--force`, sin tocar
otras ramas, sin desplegar PROD.

## 10. Segundo commit documental

El informe y la actualización de `SrvRestAstroLS_v1/docs/status_actual.md` y
`modules/telchi/status_actual.md` se publican en un commit documental posterior,
sin secretos ni datos empresariales.

## 11. Riesgos y pendientes

1. **`FREE_RESEARCH_LIVE_RUN`**: la corrección de presupuesto está cubierta por
   pruebas deterministas y por la garantía de gates; no se ejecutó una corrida de
   investigación libre con modelo real en esta ventana.
2. **Diferencia absoluta en una celda compuesta ya ejecutada**: el contrato de
   referencias distingue `subtract` y `absolute_difference` y está probado; un
   seguimiento que mezcla escalas dentro de una sola fila compuesta requiere su
   propia ventana y no se declara resuelto aquí.
3. **Entrega externa**: `EXTERNAL_WHATSAPP_E2E=NOT_TESTED`. No se enviaron
   mensajes ni se generaron conversaciones; la recepción/entrega real por
   WhatsApp no queda acreditada por estas comprobaciones.
4. **Cobertura del canal**: las limitaciones declaradas (censo DMS/U_ORIGIN,
   notas de crédito cruzadas, devoluciones no posteadas) siguen vigentes y no se
   convierten en cero.
5. **Rotación de credenciales** del cierre previo de fiabilidad de entrega sigue
   pendiente de ventana propia; no se rotó nada aquí.
6. **Sesión DEV**: `idle_timeout` 900 s / `max_duration` 14.400 s del control
   privado se mantienen; el arranque manual del owner sigue siendo el paso
   operativo, no automático.

## 12. Restricciones respetadas

| Restricción | Cumplimiento |
| --- | --- |
| SAP READ ONLY, `SAP_WRITE_COUNT=0` | Sólo lecturas de Foundation; ninguna sentencia de escritura añadida |
| Sin cambios en PROD | Todo el trabajo en DEV; sin despliegue productivo |
| Sin cambios de permisos / SourcePolicy | Comparaciones adicionales más estrictas; ningún grant ni política relajada |
| Sin hashes/manifests manuales | Manifiesto generado y publicado por el runner canónico |
| Sin desactivar gates | Las seis garantías reejecutadas; intentos bloqueados conservados |
| Servicios compartidos intactos | PostgreSQL, LiteLLM, Evolution, Cloudflare no reiniciados |
| Meta / túnel | Sin cambios; `META_CALLBACK=SYNCED` verificado por lectura |
| Sin mensajes de prueba | `whatsapp_sends=0`; sin conversaciones generadas |
| Sin operaciones Git destructivas | Sin `reset --hard`, `clean` ni `push --force` |
| Cambios de otros agentes | Preservados y publicados juntos |
| `uv run` para Python | Usado en todas las ejecuciones |
| Sin servicios/agentes/routers/bases nuevos | Sólo contratos existentes extendidos |
| Sin autostart | El runtime queda iniciado manualmente, sin configuración de autoarranque |

## 13. Sin secretos

Este informe y `report.json` no contienen credenciales, DSN, tokens, números de
teléfono, identificadores de conversación ni mensajes empresariales. Los
artefactos privados de gates permanecen en `PRIVATE_ROOT` con modo `0600`.