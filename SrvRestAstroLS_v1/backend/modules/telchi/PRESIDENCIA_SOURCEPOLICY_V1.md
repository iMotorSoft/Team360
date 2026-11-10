# Presidencia — propuesta única de alcance empresarial

Propuesta de autorización de lectura para las 70 fuentes inventariadas. No concede permisos, publica políticas ni habilita canales. La elegibilidad empresarial no certifica publicación, calidad o rendimiento.

## Contexto y autoridad

El alcance es local Telchi y documental/investigativo. Esta propuesta sustituye los criterios restrictivos A/B/C anteriores, no sus observaciones de identidad ni la evidencia histórica.

`ENTITY=TELCHI; DOMAIN=VARIOS; STAGE=INVESTIGATION; SOURCES=DATA_LAKE, CONTRATOS_EXISTENTES; OUTPUTS=DECISION, REPORT; POLICIES=PRIVATE_CONFIG, DATA_ROOT_DATA_ONLY, GIT_POLICY`.

Base: [acreditación anterior](PRESIDENCIA_ACCREDITATION_V1.md), [integración existente](PRESIDENCIA_FREE_ANALYSIS_V1.md) y [CONTEXT](CONTEXT.md). No se modificaron esos documentos ni el estado GLOBAL.

## Dictamen ejecutivo

Las 70 fuentes son elegibles como información empresarial para Presidencia; no hay exclusión de seguridad demostrada. Cinco tienen procedencia de publicación contradictoria que debe verificarse, no una prohibición de acceso.

```text
FOUNDATION_SOURCES=70
PRESIDENCIA_ELIGIBLE=70
PROVEN_EXCLUSIONS=0
DATA_QUALITY_LIMITATIONS=70
EXISTING_PERMISSION_COVERAGE=70/70_USING_12_EXISTING_ANCHORS
SOURCEPOLICY_MAPPING_GAPS=0
NEW_ROLES=0
NEW_SERVICES=0

SINGLE_SCOPE_APPROVAL=READY
OWNER_DECISIONS_REQUIRED=1_BUSINESS_SCOPE_APPROVAL
BLOCKER=NONE_FOR_SCOPE_APPROVAL; PUBLICATION_PROVENANCE_CHECK_BEFORE_ACTIVATION
```

`FOUNDATION_SOURCES=70` denomina el inventario solicitado, **no un nuevo conteo vivo de CURRENT**. `EXISTING_PERMISSION_COVERAGE` significa mapa propuesto con códigos existentes, no permisos concedidos ni 70 contratos ya aprobados. Hay 14 antecedentes de consumo y 56 extensiones de contrato propuestas.

`DATA_QUALITY_LIMITATIONS=70` cuenta fuentes sujetas a cautelas de semántica/calendario/moneda/unidad; no significa 70 defectos o exclusiones. La matriz distingue limitaciones específicas y siete referencias físicamente vacías.

La aprobación del alcance está lista; **la demostración funcional no está acreditada**. Disponibilidad de las cinco fuentes, identidades verificadas y latencia real siguen pendientes. No se encubren con el indicador READY documental.

## Decisión única propuesta

La siguiente resolución aprueba un alcance empresarial cerrado, no una activación ni el catálogo de capacidades como frontera de investigación.

> Aprobar para Presidencia la lectura empresarial interna de las 70 fuentes enumeradas en `matrix.csv`, incluidas referencias de personas/terceros, usuarios SAP identificatorios, taxonomías UNKNOWN, trazabilidad y observaciones parciales. Aprobar los contratos dataset → permiso de esa matriz mediante SourcePolicy existente, con un propietario por dataset, todas las columnas lógicas descubiertas y dataset completo, limitados a la organización Telchi y workspace telchi_dev exactos. No aprobar credenciales, administración de identidades, escrituras, otros tenants/workspaces, nuevas fuentes ni divulgación externa. La publicación privada y los grants quedan para la operación posterior explícita, después de verificar publicación, esquema e identidades.

La aceptación incluye las extensiones de contrato de los 12 permisos, no solo los nombres de las capabilities. No se solicitan 70 decisiones, decisiones separadas por Tier, roles nuevos ni excepciones de privacidad especulativas.

## Matriz completa y evidencia

La matriz tiene una fila por cada fuente, con dominio, procedencia/contrato, permiso existente, compatibilidad, Tier previo, limitaciones, estado de publicación y excepción de seguridad.

- [Matriz completa de 70 fuentes CSV](../../../../data/reports/telchi/presidencia-sourcepolicy-v1/matrix.csv).
- [Validación y esquemas de las 24 referencias](../../../../data/reports/telchi/presidencia-sourcepolicy-v1/validation.json).
- [Validador offline reproducible](investigation/validation/presidencia_sourcepolicy_v1/validate.py).
- [Tests de la propuesta sobre ResearchBinding existente](investigation/validation/presidencia_sourcepolicy_v1/test_proposal.py).

La evidencia no incluye valores personales, muestras comerciales ni secretos. La inspección nueva lee únicamente esquemas y metadatos de cabeceras/footer Parquet de Reference `v2_sales_448ae93a960bf7342564a2d0`, con un thread y 128 MB para la conexión propia; no consulta PostgreSQL, SAP ni el CURRENT vivo.

## Resolución de un permiso por dataset

Se usa un mapa explícito de muchos datasets hacia 12 permisos existentes, nunca varias políticas elegibles sobre el mismo dataset. Los permisos son anclas de autorización, no capacidades analíticas distintas.

| Permiso existente (prefijo `telchi.`, sufijo `.read.v1`) | Fuentes |
| --- | ---: |
| `sales.commercial_line_amount_by` | 23 |
| `products.search` | 6 |
| `inventory.stock_by_warehouse` | 6 |
| `purchasing.ordered_amount` | 6 |
| `purchasing.received_amount` | 5 |
| `purchasing.invoiced_amount` | 4 |
| `collections.unallocated` | 5 |
| `collections.received_amount` | 5 |
| `production.bom` | 2 |
| `production.orders` | 1 |
| `production.consumption` | 1 |
| `material_supply.consumption` | 6 |
| **Total** | **70** |

Aplicación posterior: una `SourcePolicy(source, permission, organization, workspace, columns=None, whole_dataset=True)` por fila. `organization` y `workspace` serán los UUID exactos de la acreditación, nunca slugs, parámetros del usuario ni contenido del modelo. El CSV es evidencia, no configuración privada cargada por el runtime.

Los contratos se amplían **explícitamente en esta aprobación**: por ejemplo, `ref_suppliers` queda en compras ordenadas; `ref_users`, `ref_party` y las taxonomías organizacionales quedan en trazabilidad comercial empresarial; `ref_entity_alias` en referencia de productos. Estos anclajes no afirman que esas capabilities ya consuman las fuentes ni que los nombres de los permisos describan todo su nuevo contrato de lectura.

No se implementa OR entre permisos sobre un mismo dataset. Presidencia requerirá el conjunto cerrado de 12 anclas para ejercer 70/70, sin `core_module_full_access_grants`, permiso comodín ni 21 permisos por comodidad. Los otros nueve permisos de ventas no son necesarios para el catálogo libre y no se modifican. No se diseña aquí otro perfil ni se asigna este conjunto a nadie.

`SourcePolicy` no filtra por persona o rol: la ampliación aplica a **cualquier titular efectivo de esas anclas en la misma organización/workspace**. La evidencia anterior identifica a devfull como único titular con permisos Telchi y a admin con cero; no se volvió a consultar DB. Antes de publicar, verificar titulares efectivos actuales; si hay terceros no incluidos en el alcance aprobado, detener la publicación y reportar el conflicto, sin conceder privilegios, crear roles o modificar el investigador para sortearlo.

Los schemas pueden evolucionar: `columns=None` aprueba todas las columnas lógicas descubiertas, no el acceso directo a columnas físicas descartadas ni archivos arbitrarios. Para la primera demostración se usará el pin de publicación **ya existente** en `console_http.AccreditedReader` (`foundation_publication_id` de la configuración privada). No se elige ahora un ID ni se hereda automáticamente una candidata. Cambiar el pin exige verificar la sucesión y los esquemas; una fuente nueva no obtiene política por descubrimiento.

## Revisión de Tier A, B y C

Los Tiers describían evidencia de consumo y propuestas anteriores; no constituían clases válidas de autorización empresarial. Su revisión conserva límites de calidad sin convertirlos en prohibiciones.

| Tier previo | Fuentes | Resolución |
| --- | ---: | --- |
| A | 14 | Elegibles; antecedente de consumo reutilizado, no aprobación implícita de datos completos |
| B | 41 | Elegibles como ampliación empresarial explícita de los contratos existentes |
| C | 15 | Elegibles; ninguno de los motivos previos demuestra una exclusión de seguridad |

Las 15 fuentes C se resuelven así:

- `ref_users`, `ref_suppliers`, `ref_party`, `ref_entity_alias`: referencia empresarial identificatoria. Los esquemas inspeccionados no contienen columnas de password, token, secreto o credencial. `ref_users` no concede permisos SAP ni Console; procedencia OUSR identificatoria. La presencia de nombres/identificadores fiscales no es por sí sola una prohibición de acceso interno para Presidencia. La inspección de esquema no es una auditoría de todo valor de texto libre.
- `ref_business_unit`, `ref_operating_domain`, `ref_operating_model`: UNKNOWN, vacío o incompleto es limitación de datos, no falta de autorización.
- `credit_memo_line`: contrato de reader existente; la falta de consumidor capability no impide investigación autorizada. Signos, cancelación y reconciliación siguen siendo requisitos de respuesta.
- `purchasing_document_lineage`: es un resultado de resolución; se puede investigar conservando sus estados, sin tratar cada enlace como hecho confirmado ni duplicar importes entre etapas.
- `inventory_movement`: el prefijo congelado es consultable con su cobertura explícita; no habilita reconstruir stock o inferir continuidad completa.
- `deliveries_from_quotations`, `invoices_from_quotations`, `oqut_october_2026`, `orders_from_quotations`, `qut1_october_2026`: elegibles para acceso, pero no se afirmará su publicación vigente por el mero descubrimiento histórico. Octubre no representa historia completa.

## Excepciones reales y discrepancia de publicación

No hay excepción de seguridad demostrada que requiera decisión individual del responsable. Sí hay una discrepancia técnica trazable sobre las cinco fuentes de propósito comercial.

La acreditación previa registró `foundation_c0b08df908d3485c8668788933826f7c`, snapshot de datos 1408, y 70 fuentes, incluyendo `commercial_purpose`. Al mismo tiempo su Tier C las llamó candidata no promovida: esa contradicción no se resuelve declarándolas autorizadas ni prohibidas.

La [verificación posterior conservada](../../../../data/reports/telchi/foundation-read-binding-v1/authorized-final-verification.json) identifica `foundation_42483d2e035e98e73e0a2d98ddc7d986`, commit 1506/datos 1408. Su [evidencia de integridad](../../../../data/reports/telchi/final-closure-whatsapp-e2e-v1/live-integrity.json) enumera ocho componentes, sin `commercial_purpose`. El [manifiesto offline preservado](../../../../data/reports/telchi/reference-v2-foundation-offline-final-r2/base-foundation-manifest.json) también carece de ese componente. No se inspeccionó de nuevo el manifiesto vivo en esta tarea.

Consecuencia: **5 conflictos de procedencia/publicación, 0 huecos del mapa de permisos**. No son cinco exclusiones ni cinco aprobaciones adicionales. Antes de activar, resolver el reader canónico sobre la publicación seleccionada y comparar nombres/contratos exactos: si no están, sus políticas no las hacen aparecer. Nunca apuntar a archivos de candidata, Atomic latest o una ruta inferida. Si resulta necesaria una promoción, reportarla como operación posterior fuera de esta tarea; la aprobación de acceso no la ejecuta ni sustituye su gate.

Tampoco se afirman 65 fuentes disponibles hoy: la cuenta disponible se verificará sobre CURRENT real. Las cuatro observaciones publicadas pero omitidas por `operational_domains.GROUPS`, descritas en la acreditación anterior, quedan fuera del inventario de 70; no se modifica discover ni se presenta cobertura mayor a la demostrada.

## Calidad y cobertura sin exclusiones artificiales

Los límites deben acompañar cada conclusión. Autorizar lectura permite investigar una brecha, no completar datos ausentes o convertir una observación parcial en verdad empresarial global.

En los footers de la versión Reference inspeccionada están vacíos `ref_brand`, `ref_currencies`, `ref_document_types`, `ref_payment_terms`, `ref_sales_channel`, `ref_business_unit` y `ref_production_site`. Son **7 fuentes elegibles vacías**, no exclusiones ni hechos de valor cero. La matriz y JSON preservan el conteo físico de cada referencia.

Todos los `observed_*` son observaciones acotadas; ausencia no prueba cero. La doble forma `observed_observed_material_actual_consumption` es el nombre real del catálogo, no otra fuente. BOM actual no acredita vigencia histórica. Las cantidades conservan unidades nativas; importes requieren moneda, etapa documental, cancelación y reconciliación. UNKNOWN y aliases ambiguos se reportan como tales.

## Validación y límites operativos

La validación focalizada demuestra coherencia del mapa con el contrato existente, no la disponibilidad de fuentes reales ni el desempeño conversacional.

- Validador offline: **70 nombres exactos/únicos**, Tiers **14/41/15**, **12** permisos declarados en código y previamente registrados según acreditación, **0** fuentes sin ancla; metadatos de **24** referencias, **7** vacías, sin columnas de credenciales detectadas.
- `uv run pytest modules/telchi/investigation/validation/presidencia_sourcepolicy_v1/test_proposal.py modules/telchi/exploratory_sql/test_authorized_foundation.py -q`: **45 passed**. Incluye binding de las 70 fuentes sin ambigüedad, permiso ausente, organización/workspace ajenos, literal full_access sin efecto, alcance por ancla y duplicados rechazados. Datos/identidades de fixture solamente.
- No hubo conexiones PostgreSQL, lecturas de secretos, grants, publicación SourcePolicy, cambios de roles/bindings, inicio de servicios, consultas SAP ni cambio de CURRENT. No se midió latencia ni se revalidó WhatsApp.

`lat check md`, `lat check index`, `lat check sections`, `lat check code-refs`, `lat check` y `git diff --check`: **PASS**. LAT advierte inicialización sin versión y clave de búsqueda semántica ausente, sin fallo de gates. No se reabre `900/14400` ni se corrige GLOBAL sin ventana.

## Secuencia posterior sin infraestructura nueva

La próxima operación comienza por una aprobación del alcance anterior. El resto son garantías de activación y aceptación, no ampliaciones preventivas del producto.

1. Aprobar una vez el alcance empresarial y la matriz completa; excepciones de seguridad individuales requeridas: **ninguna demostrada**.
2. Verificar publicación seleccionada, las cinco procedencias pendientes, esquemas y titulares de las 12 anclas; identidades de Presidencia verificadas por los mecanismos existentes. Esta tarea no realiza esos cambios.
3. Aplicar posteriormente las políticas privadas aprobadas sobre publicación fijada y grants explícitos autorizados, sin rol nuevo en esta propuesta ni FULL_ACCESS técnico. Si los mecanismos existentes no permiten el provisioning solicitado, informar el bloqueo real sin inventar jerarquías.
4. Probar preguntas nuevas, seguimiento, exactitud/verificación y latencia real de investigación libre. Medir extremo a extremo, p50/p95, colas/cancelación y efecto sobre otra conversación simultánea con concurrencia moderada y guard del host. Terminar correctamente pero demasiado tarde o bloqueando otra conversación **no satisface** aceptación. No se inventa ahora un umbral no acordado ni se declara PASS con timings históricos.
5. Solo después de esas pruebas, WhatsApp Presidencia. Sin web, nuevas funcionalidades comerciales, servicios o motor investigador alternativo.
