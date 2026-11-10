# Presidencia — paquete de acreditación V1 (SourcePolicy + identidades)

`STAGE=DEVELOPMENT` · `ENTITY=TELCHI` · `DOMAIN=VARIOS` · `OUTPUT=ACREDITACION` ·
`SOURCES=FOUNDATION_CURRENT, CONSOLE_RBAC` · `POLICIES=SAP_READ_ONLY, PRIVATE_CONFIG, PROMOTION_REQUIRED`

Objetivo: dejar preparada la habilitación real de Presidencia sin arquitectura nueva y sin
modificar infraestructura. Este documento **no** crea permisos, **no** compone `SourcePolicy`,
**no** crea identidades, **no** activa investigación libre y **no** ejecuta escrituras.

Método: inspección de solo lectura de los contratos existentes y de PostgreSQL DEV
(`team360`), más una resolución real de Foundation CURRENT para inventariar las 70 fuentes.
No se ejecutó ningún `INSERT`, `UPDATE`, DDL ni reinicio de servicio.

## 1. Estado medido (esta ventana)

| Hecho | Valor real observado |
| --- | --- |
| Foundation CURRENT | `foundation_c0b08df908d3485c8668788933826f7c`, snapshot `1408` |
| Fuentes descubiertas | **70**, `reader_contract_gaps = ()` |
| Permisos Telchi registrados | **21** (`core_permissions`, prefijo `telchi.`) |
| Capacidades habilitadas en `telchi_dev` | **21** (`core_workspace_capabilities`, todas `enabled`) |
| `devfull@telchiai.com` | **21** permisos efectivos, vía `core_module_full_access_grants` |
| `admin@telchiai.com` | **0** permisos efectivos; `organization_admin` de la org Telchi |
| Otros members de la org Telchi | ninguno |
| Identidades con `core_users.workspace_id = telchi_dev` | 2 reales (`admin`, `devfull`) + 2 sintéticas inactivas |
| `messaging_phone_bindings` activos | **1**: `541130946950` → `devfull` (FULL_ACCESS técnico) |
| `console_password_credentials` | **0** |
| Perfiles de permiso (`core_permission_profiles`) | 0 filas; `core_user_profiles` 0 filas |
| Roles organizacionales registrados para la org `telchi` | solo `client` |

Regresión focalizada revalidada en esta ventana: `modules/telchi/test_research_port.py` +
`assistant/tests/test_research_fallback.py` → **12 passed** (no se reejecutó la regresión de 1295).

## 2. SourcePolicy

### 2.1 Contrato vigente (no se propone otro)

`SourcePolicy(source, permission, organization, workspace, columns=None, whole_dataset=False)` es un
contrato de configuración privada del servidor, nunca entrada del modelo
(`exploratory_sql/authorized_foundation.py:38`). Reglas reales que condicionan el mapa:

1. `open_binding` calcula `allowed_sources` solo con políticas `whole_dataset=True`, del
   `organization`/`workspace` exactos y cuyo `permission` **ya posee** la identidad
   (`authorized_foundation.py:492-494`). Lo no acreditado no se descubre: fail closed.
2. `_permitted` del puerto WhatsApp exige al menos una política con permiso efectivamente vigente
   (`research_port.py:58-63`); si no hay ninguna, responde `DENIED no_authorized_source` antes de
   cualquier llamada al modelo o SQL.
3. `ResearchBinding` exige **exactamente una** política por dataset y ámbar de scope
   (`authorized_foundation.py:341-343`). Dos políticas para el mismo dataset → `ValueError`
   (`ambiguous_source_policy`), que el puerto degrada a `researcher_unavailable`. El mapa debe ser
   **1:1 estricto**.
4. `columns=None` (todas las columnas) es obligatorio en la práctica: `classify_authorized_products`
   y `enrich_authorized_sales_lines` exigen `columns is None`. No existe compilador de política por
   fila (`partial row scopes are withheld`, mismo archivo), por lo que no hay restricción por fila ni
   por columna disponible.
5. El permiso es la unidad de autorización; `permission` debe ser uno de los 21 `permission_code`
   ya registrados. Crear un permiso nuevo sería inventar acreditación.

### 2.2 Inventario de las 70 fuentes por componente

`reference` (24) — `ref_branches`(13), `ref_brand`(9), `ref_business_locations`(5),
`ref_business_unit`(9), `ref_currencies`(15), `ref_customer_business_type`(9), `ref_customers`(22),
`ref_document_types`(14), `ref_entity_alias`(15), `ref_operating_domain`(9), `ref_operating_model`(9),
`ref_party`(7), `ref_payment_terms`(15), `ref_portfolio_family`(9), `ref_product_business_type`(9),
`ref_production_site`(9), `ref_products`(32), `ref_sales_channel`(9), `ref_salespersons`(19),
`ref_suppliers`(21), `ref_units_of_measure`(6), `ref_users`(14), `ref_warehouse_roles`(10),
`ref_warehouses`(20).

`sales` (2) — `sales_document`(27), `sales_line`(20).

`credit_memo` (2) — `credit_memo_document`(27), `credit_memo_line`(24).

`oinm`/`oitw` (2) — `inventory_movement`(44), `inventory_balance`(14).

`receivables_collections` (3) — `receivable_settlement_status`(33), `collection_method_fact`(22),
`commercial_term_classification`(16).

`purchasing` (8) — `ap_invoice`(34), `ap_invoice_line`(37), `purchase_order`(34),
`purchase_order_line`(37), `purchase_receipt`(34), `purchase_receipt_line`(37),
`purchase_inventory_receipt`(35), `purchasing_document_lineage`(21).

`material_supply` (5) — `material_actual_consumption`(5), `material_equivalent_demand`(6),
`material_lead_time_profile`(9), `material_supply_status`(44), `open_purchase_pipeline`(16).

`commercial_purpose` (5) — `deliveries_from_quotations`(32), `invoices_from_quotations`(33),
`oqut_october_2026`(32), `orders_from_quotations`(36), `qut1_october_2026`(40).

`operational_observations` (19 de 23 publicadas) — `observed_ap_invoice`(15),
`observed_ap_invoice_line`(27), `observed_bom_header`(11), `observed_bom_line`(15),
`observed_collection_allocation`(14), `observed_collection_payment`(38),
`observed_inventory_movement`(31), `observed_observed_material_actual_consumption`(9),
`observed_payment_method_component`(14), `observed_payment_term`(11), `observed_production_issue`(25),
`observed_production_order`(25), `observed_purchase_order`(22), `observed_purchase_order_line`(27),
`observed_purchase_receipt`(15), `observed_purchase_receipt_line`(23),
`observed_receivable_document`(36), `observed_reconciliation_event`(17),
`observed_reconciliation_participant`(18).

24 + 2 + 2 + 2 + 3 + 8 + 5 + 5 + 19 = **70**.

### 2.3 Tier A — acreditadas por contrato existente (14)

Cada fila tiene evidencia en código de que un permiso **ya registrado** lee ese dataset en runtime.
Son las únicas que no requieren juicio semántico nuevo.

| Dataset | Cols | Permiso (existente) | Evidencia de lectura |
| --- | --- | --- | --- |
| `sales_document` | 27 | `telchi.sales.commercial_line_amount_by.read.v1` | `commercial_line_amount_by_query.py:275`, `sales_query.py:91`, `invoice_*_query.py` |
| `sales_line` | 20 | `telchi.sales.commercial_line_amount_by.read.v1` | `commercial_line_amount_by_query.py:275`, `product_sales_query.py:123` |
| `credit_memo_document` | 27 | `telchi.sales.commercial_line_amount_by.read.v1` | `commercial_line_amount_by_query.py:390`; `sales_query.py:91` |
| `ref_products` | 32 | `telchi.products.search.read.v1` | `product_sales_query.py:111`, `category_line_amount_query.py:226` |
| `ref_customers` | 22 | `telchi.sales.commercial_line_amount_by.read.v1` | `commercial_line_amount_by_query.py:235` |
| `inventory_balance` | 14 | `telchi.inventory.stock_by_warehouse.read.v1` | `operational_query.py:121` |
| `observed_purchase_order` | 22 | `telchi.purchasing.ordered_amount.read.v1` | `operational_query.OPERATIONS` |
| `observed_purchase_receipt` | 15 | `telchi.purchasing.received_amount.read.v1` | idem |
| `observed_ap_invoice` | 15 | `telchi.purchasing.invoiced_amount.read.v1` | idem |
| `observed_collection_payment` | 38 | `telchi.collections.received_amount.read.v1` | idem |
| `observed_production_issue` | 25 | `telchi.production.consumption.read.v1` | idem |
| `observed_production_order` | 25 | `telchi.production.orders.read.v1` | idem |
| `observed_bom_line` | 15 | `telchi.production.bom.read.v1` | idem |
| `observed_observed_material_actual_consumption` | 9 | `telchi.material_supply.consumption.read.v1` | idem |

Nota de equidad: 9 permisos de venta distintos leen `sales_document` y 5 leen `sales_line`. Como el
mapa admite un solo permiso por dataset, se elige el contrato de líneas comerciales por ser el más
amplio ya acreditado. Consecuencia real: una identidad que solo posea `sales.coverage` o
`sales.invoice_lines` **no** verá `sales_document`/`sales_line` en investigación libre. Es
estrechamiento fail-closed, no elevación.

Consecuencia estructural: los 21 permisos **no** son direccionables de forma independiente sobre el
mismo dataset físico. Aun aprobando Tier A+B, el catálogo libre puede ejercer como máximo **12** de
los 21 permisos; los 9 restantes (`sales.latest_documents`, `sales.coverage`,
`sales.period_billed_amount`, `sales.invoice_amount`, `sales.invoice_lines`, `sales.by_products`,
`sales.category_line_amount`, `sales.product_line_amount_ranking`, `sales.source_quantity`) siguen
existiendo solo en la capa de capacidades, no en la investigación libre.

### 2.4 Tier B — propuestas por dominio (41), requieren aprobación del responsable

Ninguna de estas fuentes fue leída nunca por una capacidad acreditada. El permiso asignado existe,
pero la acreditación de lectura es una decisión de negocio, no un hecho demostrado en código.

- **B1 · Catálogo producto (4, un permiso `telchi.products.search.read.v1`)**: `ref_brand`,
  `ref_product_business_type`, `ref_units_of_measure`, `ref_portfolio_family`.
- **B2 · Dimensiones comerciales (8, un permiso `telchi.sales.commercial_line_amount_by.read.v1`)**:
  `ref_branches`, `ref_business_locations`, `ref_customer_business_type`, `ref_currencies`,
  `ref_document_types`, `ref_payment_terms`, `ref_sales_channel`, `ref_salespersons`.
- **B3 · Almacén y sitio (3, un permiso `telchi.inventory.stock_by_warehouse.read.v1`)**:
  `ref_warehouses`, `ref_warehouse_roles`, `ref_production_site`.
- **B4 · Compras (10)**: `purchase_order`, `purchase_order_line`, `observed_purchase_order_line` →
  `telchi.purchasing.ordered_amount.read.v1`; `purchase_receipt`, `purchase_receipt_line`,
  `purchase_inventory_receipt`, `observed_purchase_receipt_line` →
  `telchi.purchasing.received_amount.read.v1`; `ap_invoice`, `ap_invoice_line`,
  `observed_ap_invoice_line` → `telchi.purchasing.invoiced_amount.read.v1`.
- **B5 · Cobranzas (10)**: `receivable_settlement_status`, `observed_receivable_document`,
  `observed_collection_allocation`, `observed_payment_term` →
  `telchi.collections.unallocated.read.v1`; `collection_method_fact`,
  `observed_payment_method_component`, `observed_reconciliation_event`,
  `observed_reconciliation_participant` → `telchi.collections.received_amount.read.v1`;
  y `observed_collection_payment` ya está en Tier A con `received_amount`.
- **B6 · Producción (1)**: `observed_bom_header` → `telchi.production.bom.read.v1`.
- **B7 · Material Supply (5), un permiso `telchi.material_supply.consumption.read.v1`**:
  `material_actual_consumption`, `material_equivalent_demand`, `material_lead_time_profile`,
  `material_supply_status`, `open_purchase_pipeline`.

`material_supply_status` está en B7 y no en A: es el segundo input obligatorio de
`classify_authorized_products` (`authorized_foundation.py:163`). Aprobarlo habilita
`product_business_type` derivado en el catálogo libre; sin él solo se registra un gap, no un fallo.

### 2.5 Tier C — sin política suficiente (15), exclusión por defecto

| Fuente(s) | Motivo concreto de no acreditar ahora |
| --- | --- |
| `ref_users`, `ref_suppliers`, `ref_party`, `ref_entity_alias` | Datos de personas/terceros y resolución de alias. Ningún permiso empresarial existente los lee; exponerlos `whole_dataset` con todas las columnas es una decisión de privacidad, no de analítica. |
| `ref_business_unit`, `ref_operating_domain`, `ref_operating_model` | Taxonomía de negocio sin permiso dueño y con estado semántico `business unknown` declarado en el estado local. |
| `credit_memo_line` | Existe en el contrato del reader (`_COMPONENT_TABLES`) pero **ninguna** consulta de negocio lo lee; solo extracción/validación. Acreditarlo inventaría un contrato. |
| `purchasing_document_lineage` | Tabla derivada con `resolution_status`/`effective_status`/`edge_resolution_status`; no es un hecho publicado, es un resultado de resolución. |
| `inventory_movement` | Límite propio del componente: `FROZEN_NATIVE_KEY_PREFIX_ONLY`, sin continuidad de ventana completa ni derivación de stock. |
| `deliveries_from_quotations`, `invoices_from_quotations`, `oqut_october_2026`, `orders_from_quotations`, `qut1_october_2026` | Componente `commercial_purpose` = candidato semántico **sin promoción** (`foundation_15cfdba7…`), y dos de ellos son extractos de octubre 2026: la cobertura de calendario no es generalizable. |

### 2.6 Limitaciones semánticas reales (aplican al mapa completo)

1. **Descubrimiento ≠ acreditación de negocio**: `discover` declara por contrato que la granularidad,
   relaciones, monedas, unidades y cobertura de calendario no están acreditadas.
2. **Importe de línea no es facturación neta**: `line_total` es dinero comercial **antes** de notas de
   crédito; `sales_document.doc_total` es documental. No se debe presentar como ingreso ni cobranza.
3. **Identificador de cliente ≠ comprador final DMS**; la clasificación publicada puede ser actual y
   no histórica.
4. **Observación acotada ≠ historia completa**: los `observed_*` provienen de capturas acotadas
   (`BOUNDED_OBSERVATION`, `absence_is_zero=False`). Una ausencia no acredita cero.
5. **23 datasets de observación publicados, solo 19 expuestos**: `operational_domains.GROUPS` no
   incluye `historical_inventory_balance`, `observed_material_lead_time_anomaly`,
   `observed_material_lead_time_profile` ni `production_receipt`. No son accesibles al catálogo libre
   aunque se apruebe una política, porque `discover` los descarta.
6. **Artefacto de nombre**: `observed_observed_material_actual_consumption` lleva doble prefijo porque
   el dataset ya se llama `observed_material_actual_consumption`. Es el mismo dato; no duplicar política.
7. **Sin restricción por columna ni por fila**: cada política aprobada expone el dataset completo.

### 2.7 Cobertura del mapa propuesto

| Escenario | Datasets acreditados | Cobertura |
| --- | --- | --- |
| Solo D1 (Tier A, sin juicio nuevo) | 14 | 20,0 % |
| D1 + D2 (B1..B7 aprobados) | 55 | 78,6 % |
| Tier C (excluido por defecto) | 15 | 21,4 % |

`ENTERPRISE_DATASET_COVERAGE = 14/70 mínimo acreditado por contrato · 55/70 con Tier B aprobado`.

## 3. Presidencia — identidades

### 3.1 Modelo vigente (inspeccionado, sin cambios)

La cadena de autorización real para el canal WhatsApp es:

1. `messaging_phone_bindings` (environment `dev`, provider `evolution`, tenant `telchi`,
   `verification_status='verified'`, `verification_ref` no vacío) resuelve `sender_identity` →
   `user_id` (`messaging/identity.py:27-57`). Sin fila → el mensaje no tiene identidad.
2. `core_users` debe tener `workspace_id = telchi_dev`, `status` activo.
3. `core_organization_members` debe tener una fila activa en la org `telchi`
   (`exploratory_sql/console_repository.py:13-21`); sin ella `identity()` devuelve `None`.
4. Permisos efectivos = unión de tres vías (`roles`, `profiles`, `FULL_ACCESS` del módulo) en
   `PermissionConsoleRepository.LIST_EFFECTIVE_PERMISSIONS_SQL`, intersectada con
   `core_workspace_capabilities.enabled` (`research_port.py:44-64`).

Hechos que restringen el provisioning:

- `core_users.workspace_id` es **único por persona**: una identidad existe con un solo workspace
  primario, y la autorización exige que coincida con `telchi_dev`. Un usuario de otro workspace **no**
  puede actuar como Presidencia sin re-hospedarlo, lo que rompería sus demás memberships.
- `AdminRepository.user()` del provisioning Telchi rechaza explícitamente crear o mover identidades:
  «existing active identity in this workspace required; no move or enrollment».
  `console/login_cli.py` también opera «existing active user only». **La creación de identidades no es
  un camino Telchi**; pertenece a Console/Auth.
- `uq_core_users_email_lower_present` es único global por `lower(email)`: dos correos reales y
  verificables, no reutilizables.
- El rol organizacional `organization_admin` es el que exige `bind_verified_dev_phone`
  (`provisioning/phone_binding.py:20-24`). Hoy solo lo tiene `admin@telchiai.com`.
- No existe `organization_owner` **registrado** para la org `telchi` en `core_organization_roles`
  (solo `client`); los `role_code` de membership son texto libre sin FK. Si «Dueño de Telchi» debe
  expresarse como `organization_owner`, falta también esa decisión de Console/Auth.

### 3.2 Estado real de las dos identidades

| Sujeto | Identidad existente | Estado |
| --- | --- | --- |
| Dueño de Telchi | ninguna en la org/workspace Telchi | **PENDING** |
| Abraham | ninguna fila en `core_users` | **PENDING** |

Candidatos reales existentes en la base, **no asumidos**: `mario.rojas@alquimiablue.com`
(`9a70f03a-3567-4394-8913-58abe0e0c0c1`, `organization_owner` + `technical_admin` de la org
`team360_live`) y `mario.rojas.marconi@gmail.com` (`0469ad98-8750-41ae-899b-198a831f1acc`,
`team360_live`). Ambos tienen workspace primario `team360_public_site`, por lo que no son asignables
a `telchi_dev` sin una decisión de re-hospedaje. Las dos identidades `synth-*` de `telchi_dev` son
fixtures sintéticas inactivas y no pueden usarse.

`PRESIDENCIA_IDENTITIES = PENDING`.

### 3.3 Provisioning mínimo (definido, no ejecutado)

1. **Identidades** (Console/Auth, no Telchi): dos `core_users` nuevos con correo real verificado,
   `workspace_id = 3fb026a1-a4ba-44b3-b65b-fab452df7fc9` (`telchi_dev`), `status='active'`.
2. **Membership**: dos `core_organization_members` activos en la org
   `44b9b7ea-1c19-4a9f-a3d5-1f20622d2f99` (`telchi`).
3. **Acceso empresarial idéntico**: **un** rol de workspace nuevo, con las mismas filas
   `core_role_permissions` para ambos usuarios, sobre el conjunto de permisos que el responsable
   apruebe (Tier A ⇒ 11 permisos distintos; Tier A+B ⇒ 12). Sin perfiles y sin roles distintos por
   persona: la igualdad se demuestra con un único rol asignado dos veces.
4. **Canal**: dos `messaging_phone_bindings` verificados (`dev`/`evolution`/`telchi`), cada uno con
   consentimiento externo y `verification_ref`, ejecutados por un actor `organization_admin` de la org
   Telchi (`admin@telchiai.com` es el único elegible hoy).
5. **SourcePolicy**: componer el mapa aprobado en el JSON privado owner-only que consume
   `console_http.load_config()` (`policies`), sin tocar código.

### 3.4 Separación de FULL_ACCESS técnico

`core_module_full_access_grants` concede **todos** los permisos del módulo habilitados en el
workspace, presentes y futuros, más el literal `telchi.full_access`. Un rol explícito concede una
lista cerrada y no se amplía cuando aparece una capability nueva. Por eso Presidencia debe ir por
roles y **sin** fila de `core_module_full_access_grants`:

- `OWNER_ACCESS` = rol de workspace con el conjunto aprobado (11 permisos con Tier A; 12 con
  Tier A+B) · sin `core_module_full_access_grants` · `organization_owner` solo si esa decisión se toma.
- `ABRAHAM_ACCESS` = **el mismo** rol, mismos permisos efectivos.
- `TECHNICAL_FULL_ACCESS_SEPARATED = YES` (devfull conserva su grant técnico; Presidencia no lo usa).
- Un literal `FULL_ACCESS` en nombres de permiso no expande scope (`test_full_access_string_does_not_expand_scope`);
  lo que expande es la fila en `core_module_full_access_grants`, no un string.

### 3.5 Identificadores y aprobaciones que faltan (exactos)

1. Correo real y verificado del **Dueño de Telchi** (para `core_users.email`, único por `lower()`).
2. Correo real y verificado de **Abraham**.
3. Número WhatsApp E.164 de cada uno + consentimiento externo + `verification_ref` auditable.
4. Aprobación del conjunto de permisos empresariales (idéntico para ambos) y de su rol.
5. Decisión sobre `organization_owner`: registrarlo para la org `telchi` o aceptar solo membership.
6. Confirmación de que ninguna de las dos personas es una identidad existente de otro workspace
   (si lo fuera: decidir re-hospedaje explícito, no asumirlo).

## 4. Rendimiento — confirmación del enganche existente

| Garantía | Verificación real |
| --- | --- |
| Sin llamadas LLM extra en consultas conocidas | El hook solo se evalúa si `audit['bmd']['category'] == 'CAPABILITY_MISSING'` (`handler.py:189-195`). La planificación de capacidades ya falló antes; no hay router LLM que elija el camino. Con `researcher is None` retorna de inmediato. Test: `test_no_research_when_the_catalog_gap_is_not_the_reason` afirma `researcher.calls == []`; el camino con gap afirma `capability_calls == 0`. |
| Sin HTTP entre componentes | `research_port` importa `ConsoleResearchService` y ejecuta in-process con el pool compartido; `build_researcher` no levanta runtime HTTP. `grep` de `httpx/requests/aiohttp/urllib` en `research_port.py`, `console_http.py`, `console_bridge.py`, `authorized_foundation.py` → 0 coincidencias. `CONSOLE_HTTP_DEPENDENCY=NO`. |
| No bloquea el ingreso WhatsApp | Con `TEAM360_TELCHI_DURABLE=1`, `MessagingService.process` persiste el inbound y devuelve `'queued'` (`messaging/service.py:149-150`); el webhook ACKea y `DurableWorker` corre el handler con inbox/resultado en PostgreSQL. **Sin** durable el handler corre dentro del request: el ingreso queda tomado hasta `turn_timeout_seconds` (80 s) y la investigación libre se cancela a los 80 s. |
| 300 s ≠ duración de conversación | `turn_timeout_seconds = 300 if durable else 80` (`composition.py:46`) es presupuesto por turno. La sesión DEV de WhatsApp usa inactividad 900 s y duración máxima 14.400 s (`whatsapp_dev.py:36-37`). Son relojes distintos: un turno puede agotarse sin cerrar la conversación. |

Riesgo medido, no defecto nuevo: las corridas reales de investigación registradas midieron 111–317 s.
Un caso de 317 s ya excede el presupuesto de 300 s y se cancelaría de forma segura (el puente cancela
el SQL y une su worker). Además, `ConsoleResearchService._slot` es **un** `asyncio.Lock` por servicio:
con dos usuarios de Presidencia, la segunda investigación espera a la primera dentro de su propio
presupuesto de turno.

No se rediseñó el worker, no se agregó componente y no se midió latencia de la ruta libre: es
imposible sin el mapa acreditado y sin las dos identidades.

## 5. Dictamen

```text
SOURCE_POLICY_CANDIDATE=PARTIAL        14/70 por contrato; 55/70 si se aprueba Tier B
FOUNDATION_SOURCES=70                  discover() en vivo, 0 reader_contract_gaps
ENTERPRISE_DATASET_COVERAGE=14/70      20,0 % mínimo; 55/70 (78,6 %) con Tier B
MISSING_POLICY_DECISIONS=8             D1 core + 6 bundles de dominio + 1 de exclusiones (Tier C)

PRESIDENCIA_IDENTITIES=PENDING         ninguna de las dos existe en la org/workspace Telchi
OWNER_ACCESS=NOT_PROVISIONED           rol de workspace pendiente de aprobación y de identidad
ABRAHAM_ACCESS=NOT_PROVISIONED         idéntico al anterior, misma asignación
TECHNICAL_FULL_ACCESS_SEPARATED=YES    Presidencia por roles; devfull conserva el grant técnico

FREE_ANALYSIS_ENGINE=REUSED            exploratory_sql único, in-process
NEW_SERVICES=0
RESOURCE_GAPS=1 slot serializado de investigación · presupuesto por turno 300 s < 317 s observado ·
              4 datasets de observación publicados no expuestos · sin política por columna/fila ·
              sin medición de latencia libre (bloqueada por acreditación e identidades)
READY_FOR_OWNER_APPROVAL=YES           el paquete de decisiones está delimitado
BLOCKER=aprobación del mapa dataset→permiso + dos identidades reales verificadas (Console/Auth)
SIX_GATES=DEGRADED                     sin reacreditar para el fingerprint final de esta ventana
```

## 6. Decisiones humanas imprescindibles

Solo estas. No hay fase de arquitectura pendiente.

1. **D1** — Aprobar Tier A (14 datasets) como núcleo acreditado sin juicio semántico nuevo.
2. **D2** — Aprobar B1: catálogo producto (4) bajo `telchi.products.search.read.v1`.
3. **D3** — Aprobar B2: dimensiones comerciales (8) bajo
   `telchi.sales.commercial_line_amount_by.read.v1`.
4. **D4** — Aprobar B3: almacén y sitio (3) bajo `telchi.inventory.stock_by_warehouse.read.v1`.
5. **D5** — Aprobar B4: compras (10) según el reparto por permiso ya existente.
6. **D6** — Aprobar B5: cobranzas (10) según el reparto por permiso ya existente.
7. **D7** — Aprobar B6+B7: `observed_bom_header` (1) y Material Supply (5).
8. **D8** — Confirmar exclusiones Tier C (15), en especial `ref_users`/`ref_suppliers`/`ref_party`/
   `ref_entity_alias` y `commercial_purpose` (5), que requieren ventana propia si se quisieran.
9. **I1** — Correo real verificado del Dueño de Telchi (→ `core_users` en `telchi_dev`).
10. **I2** — Correo real verificado de Abraham (→ `core_users` en `telchi_dev`).
11. **I3** — Números WhatsApp E.164 + consentimiento externo + `verification_ref` de cada uno.
12. **I4** — Aprobar el rol empresarial idéntico para ambos y la decisión `organization_owner`.

Con D1–D8 + I1–I4 se puede componer `SourcePolicy`, crear el rol y ejecutar el enlace de teléfonos,
y solo entonces medir A–E con datos reales antes de habilitar el canal.

## 7. Límites de esta ventana

- Solo lectura: ninguna escritura en PostgreSQL, ningún archivo de configuración privada modificado,
  ningún permiso, rol, identidad ni binding creado.
- No se reinició WhatsApp, no se tocó Meta, no se publicaron gates, no se activó
  `TEAM360_TELCHI_FREE_ANALYSIS`.
- No se modificó `SrvRestAstroLS_v1/backend/modules/telchi/status_actual.md` para no pisar escritores
  concurrentes en el mismo worktree.
- `SIX_GATES` no se reacredita aquí: la evidencia de esta ventana es inspección de contratos y estado
  real, no una corrida de gates.