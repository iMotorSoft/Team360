# Presidencia — análisis libre por WhatsApp V1 (integración mínima)

`STAGE=DEVELOPMENT` · `ENTITY=TELCHI` · `DOMAIN=VARIOS` (el investigador no es un dominio) ·
`OUTPUT=CAPACIDAD_RUNTIME` · `SOURCE=DATA_LAKE` · `POLICIES=SAP_READ_ONLY, PRIVATE_CONFIG, PROMOTION_REQUIRED`

Objetivo: que Presidencia converse libremente con Luna sobre información empresarial autorizada
por WhatsApp, reutilizando **un solo investigador** (`exploratory_sql`) sin HTTP hacia Console,
sin motor nuevo, sin servicio nuevo y sin capacidades por pregunta.

## 1. Qué se reutilizó (sin reconstruir nada)

| Pieza | Fuente | Uso |
| --- | --- | --- |
| Planificación/ejecución/verificación | `exploratory_sql/ask.py::Session.ask` → `adaptive_research.run` | Núcleo investigador, sin cambios |
| Ejecutor SQL de solo lectura | `authorized_foundation.AuthorizedFoundationExecutor` | AST, deadlines, budgets, guard de recursos |
| Autorización ligada al turno | `authorized_foundation.ResearchBinding` (`check`, `present`) | Revalida antes de ejecutar y antes de divulgar |
| Catálogo autorizado | `open_binding` + `SourcePolicy` + `discover` | Solo datasets con contrato aprobado y permiso efectivo |
| Puente in-process | `exploratory_sql/console_bridge.py::ConsoleResearchService` | Worker, cancelación, auditoría PG, memoria acotada |
| Foundation CURRENT | `datalake/foundation_reader.py` (sucesión + recibo de lectura) | Sin hashes hardcodeados |
| RBAC | `modules/console/repositories.py::PermissionConsoleRepository` | Única fuente de permisos efectivos |
| Auditoría | `exploratory_sql/console_repository.py::audit` (`core_events`) | `telchi.research.authorization` |

No se importan runners de `investigation/` desde código de producción.

## 2. Cambio de integración (mínimo y reversible)

1. `exploratory_sql/console_bridge.py`
   - `ask(token, …)` pasa a ser un adaptador fino; el cuerpo vive en `ask_scope(scope_resolver, …)`.
   - El núcleo deja de depender de un token: recibe un `scope_resolver` async que devuelve
     `EffectiveScope` fresco. Console sigue usando su token; WhatsApp usa su identidad ya autenticada.
   - `public_keys_by_id` deja de ser obligatorio en el constructor (lo exige `console_http.py`, que es
     quien realmente valida tokens). `resolve()` falla cerrado si no hay claves.
2. `console_http.py`
   - Se elimina `ACCREDITED_CURRENT` (hash literal). `AccreditedReader(publication=None)` acepta el
     CURRENT que selecciona el contrato de sucesión; el binding del turno fija publicación+snapshot.
     Un pin opcional sigue disponible por configuración privada.
   - `evidence_directory`/`evidence_sink` se exponen como funciones para reutilizarlas sin HTTP.
3. `research_port.py` (nuevo, nivel `modules/telchi/`, fuera de `assistant/` para no romper la
   frontera arquitectónica existente): `WhatsAppResearchPort` adapta la identidad del canal al mismo
   `ask_scope`, con pre-check de `SourcePolicy` y sink privado. `build_researcher()` es opt-in
   explícito (`TEAM360_TELCHI_FREE_ANALYSIS=1`, solo DEV) y devuelve `None` si no se habilitó.
4. `assistant/handler.py`
   - Parámetro opcional `researcher=None`; sin él el comportamiento es idéntico.
   - Un único punto de enganche en `_process`: si la planificación de capabilities terminó en
     `CAPABILITY_MISSING`, se intenta el investigador. No hay llamada adicional a otro modelo para
     elegir el camino y no se consulta SQL si el catálogo ya resolvió.
   - Si el investigador devuelve `BLOCKED`, vacío o falla, se conserva la respuesta de brecha
     acreditada; nunca se inventa un resultado. El intento queda auditado (`audit['research']`).
5. `assistant/composition.py`: construye el port solo con el opt-in y lo inyecta.

## 3. Dos caminos, un investigador

- Consulta conocida → `SalesCapabilities` (camino optimizado, sin SQL libre).
- Pregunta fuera del catálogo → `exploratory_sql` (planificación dinámica + validación + verificación).
- La decisión la toma el resultado ya calculado de la planificación de capabilities; no se agrega un
  router LLM ni un salto HTTP. `CONSOLE_HTTP_DEPENDENCY=NO`.

## 4. Seguridad

- Identidad: `SenderIdentity` ya autenticada por el dispatcher de Messaging; los UUID de
  organización/workspace se resuelven desde PostgreSQL (fila de identidad), nunca desde texto ni slugs.
- Permisos: `list_effective_permissions ∩ enabled_permissions`; sin grants nuevos ni `FULL_ACCESS`.
- Fuentes: solo `SourcePolicy` con `whole_dataset` y permiso realmente vigente; si no hay ninguna, se
  rechaza antes de cualquier llamada al modelo o SQL (`no_authorized_source`).
- Revalidación: el `ResearchBinding` revalida en cada acceso y `present()` antes de divulgar; el port
  re-resuelve el scope antes de cada turno (revocación efectiva).
- Solo lectura: se conserva el ejecutor validado (AST, allowlist, `enable_external_access=false`,
  deadlines, budgets, límites de filas/bytes).
- Auditoría: `core_events` con estado y `investigation_id`; evidencia completa en sink privado
  owner-only fuera del repositorio. Ningún token, SQL, prosa cruda ni valores comerciales en PG.

## 5. Defectos encontrados y corregidos

1. `console_http.py` fijaba la publicación actual como literal (`ACCREDITED_CURRENT`). Corregido:
   CURRENT lo selecciona el contrato de sucesión; el turno lo fija en el binding.
2. El núcleo del investigador estaba acoplado a un token Console. Corregido con `ask_scope`.
3. El port recibía un *sink* donde se esperaba una *fábrica de sinks* (detectado por test). Corregido.
4. Suposición inválida de que `tenant_id`/`workspace_id` del canal son los UUID de Console. Corregido:
   la fila de identidad en PG es la autoridad.

## 6. Bloqueos imprescindibles (no sorteables por código)

Ambos son decisiones del responsable/Console, no defectos del investigador:

1. **Composición `SourcePolicy` acreditada.** No existe un mapa aprobado
   `dataset Foundation → permiso comercial` con `whole_dataset=True`. Sin ese contrato, el catálogo
   autorizado queda vacío y el investigador responde `BLOCKED` (fail closed). Inventarlo o derivarlo
   automáticamente sería fabricar una acreditación.
2. **Identidades de Presidencia.** La inspección real de PostgreSQL DEV muestra en `telchi_dev` solo
   `admin@telchiai.com` (0 permisos Telchi) y `devfull@telchiai.com` (21 permisos, piloto DEV).
   No hay perfil/rol de Presidencia ni identidad de Abraham: `PRESIDENCIA_ACCESS` no es demostrable
   sin provisioning coordinado de Console/Auth. No se elevaron identidades ni se crearon permisos.

## 7. Evidencia real medida (in-process, sin WhatsApp ni reinicios)

- Foundation CURRENT resuelto en vivo: `foundation_c0b08df908d3485c8668788933826f7c`, snapshot `1408`.
- `discover()`: **70 sources**, **0** `reader_contract_gaps`.
- Permisos Telchi efectivos: `devfull` **21**, `admin` **0**.
- Gates reales del port (0 llamadas al modelo, 0 SQL):
  - sin `SourcePolicy` → `DENIED no_authorized_source`;
  - permiso de supervisión no poseído → `DENIED no_authorized_source`;
  - scope con permiso vigente → permitido; revocación entre turnos → `DENIED` en el turno siguiente.
- Regresión focalizada: **1295 passed, 4 skipped**
  (`assistant/tests`, `exploratory_sql`, `test_console_http.py`, `test_dev_app.py`).
- Nuevos tests: `assistant/tests/test_research_fallback.py` (5) y `test_research_port.py` (7).

No se midieron latencias de investigación libre real con Presidencia porque el catálogo autorizado no
existe todavía (bloqueo 1). No se declara PASS de rendimiento conversacional sin esa medición.

Nota de presupuesto técnico (no es un deadline conversacional nuevo): el turno del canal usa el
`turn_timeout_seconds` ya existente. Con el valor por defecto de 80 s una investigación libre se
cancela de forma segura (el puente cancela SQL y une su worker); las corridas históricas reales
midieron 111–317 s, por lo que el camino libre requiere la ventana durable de 300 s ya existente.

## 8. Dictamen

```text
PRESIDENCIA_ACCESS=FAIL            (1) identidades no provisionadas
FREE_ANALYSIS_ENGINE=REUSED        núcleo único, sin motor nuevo
WHATSAPP_INTEGRATION=PARTIAL       port + handler in-process; transporte real no ejecutado
CONSOLE_HTTP_DEPENDENCY=NO
NEW_SERVICES=0

KNOWN_QUERY=PASS                   camino de capabilities intacto (1295 tests)
FREE_SQL_INVESTIGATION=BLOCKED     (1) composición SourcePolicy no acreditada
CONTEXTUAL_FOLLOWUP=BLOCKED        depende de (1)
FOUNDATION_VERIFICATION=PASS       CURRENT 1408 + 70 sources + 0 gaps, en vivo
AUTHORIZATION=PASS                 fail-closed verificado en vivo (parcial: sin perfil Presidencia)
RESOURCE_SAFETY=PASS               guard existente intacto; preflight host SAFE

PERFORMANCE_DIRECT=…               no medido (sin Presidencia/WhatsApp real)
PERFORMANCE_EXPLORATORY=…          no medido (bloqueo 1)
PERFORMANCE_FOLLOWUP=…             no medido (bloqueo 1)

SIX_GATES=DEGRADED                 evidencia no reacreditada para el fingerprint final
READY_FOR_PRESIDENCIA_DEMO=NO
BLOCKER=SourcePolicy acreditada + identidades de Presidencia (owner/Console)
```

## 9. Próximo paso

1. El responsable aprueba el mapa `dataset → permiso` (o los contratos parciales) y las dos identidades
   de Presidencia con idéntico alcance de lectura.
2. Con eso, `TEAM360_TELCHI_FREE_ANALYSIS=1` habilita el camino libre y se miden A–E con datos reales
   (latencia, llamadas al modelo, SQL) antes de habilitar el canal WhatsApp real.