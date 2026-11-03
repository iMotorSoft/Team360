# Clasificación física de productos V1

Contrato físico aditivo y publicación Reference-only mediante el mecanismo canónico. La integración vigente y sus límites conversacionales están en el [estado local](../status_actual.md); este contrato no autoriza nuevas consultas SAP.

## Contrato Reference

Los campos son aditivos en `products`. Las versiones históricas no se reescriben; ausencia del contrato significa no observado, nunca una clasificación inferida.

| Campo | Tipo persistido | Regla |
| --- | --- | --- |
| `sap_forma_farmac_code` | VARCHAR nullable | Código original de `OITM.U_FormaFarmac`, sin trim ni coerción a un código conocido |
| `physical_classification_label` | VARCHAR nullable | Etiqueta oficial, únicamente para códigos reconocidos |
| `physical_state` | VARCHAR nullable | `LIQUID`, `SEMISOLID`, `SOLID`, o NULL |
| `physical_classification_status` | VARCHAR nullable | `CLASSIFIED`, `UNCLASSIFIED`, `NOT_PHYSICAL`, `NOT_APPLICABLE`, `MISSING`, `UNKNOWN` |
| `physical_classification_source` | VARCHAR nullable | `SAP_HANA.OITM.U_FormaFarmac` |
| `physical_classification_observed_at` | VARCHAR nullable | Instante UTC de observación/extracción; no fecha de efectividad empresarial |

Los códigos `0/1/2/3/4/5` representan `NINGUNA/LIQUIDO/SEMI-SOLIDO/SOLIDO/MEDICAMENTO/NO CORRESPONDE`. Sólo `1/2/3` fijan estado físico. Códigos inválidos conservan su representación original; NULL y blancos son MISSING, sin completar desde legacy.

`canonical_product_id`, clasificaciones comerciales y crosswalks existentes se preservan. El refresh valida unicidad por sistema y clave, referencias, identidad anterior y ausencia de colisiones SAP/legacy. No hay matching por nombre, unidad ni similitud.

El versionado usa contenido y schema, no rutas de fixtures, serialización o timestamps de observación. Un NOOP conserva la observación de la versión sellada; la nueva comprobación queda en evidencia. Se comprueba el contenido de destinos existentes antes de activar el pointer.

## Publicación Foundation

La transición `FOUNDATION_REFERENCE_REFRESH_V1` reutiliza el store, estados, commit lógico y rollback existentes. `publish_reference_only` es una función explícita del updater existente, sin extractor ni invocación automática desde el asistente.

Los ocho componentes inspeccionados son Reference, Sales, Credit Memo, OINM, OITW, Material Supply, Receivables & Collections y Purchasing.

- Reference cambia únicamente tras acreditar compatibilidad del contrato anterior.
- Sales, Credit Memo, OINM y OITW conservan sus publicaciones de Atomic y el snapshot anterior.
- Material Supply conserva datasets y referencias físicas exactas; se valida con su resolver existente.
- Receivables & Collections conserva fingerprint, derivación y datasets Business; se valida con su resolver existente y mantiene `base_snapshot_id`.
- Purchasing conserva su contrato estable, dependencias originales, hashes y referencias exactas. Se validan también registry de datasets y versión del algoritmo.

No se reescriben las dependencias de Purchasing para fingir que fue derivado con otra Reference. La nueva envoltura enlaza la publicación anterior y una prueba reproducible de conservación de proyecciones. Los readers existentes de Material Supply y Cobranzas aceptan la transición mediante el validador compartido.

El reader canónico resuelve el commit nuevo, pero fija las relaciones Atomic al snapshot de datos anterior mediante `reference_data_snapshot_id`. Este campo es distinto de `base_snapshot_id`, que conserva el snapshot de derivación. En replay offline el caller debe acreditar el snapshot de datos explícitamente; con connector real se resuelve por el reader canónico. Las transiciones encadenadas no pueden cambiarlo. Así no expone facts posteriores preparados por otro candidato. El store rechaza un commit si CURRENT cambió desde la preparación, dentro de la misma transacción.

## Compatibilidad y rechazo explícito

La prueba es deliberadamente conservadora: no declara compatibles cambios semánticos que no pueda demostrar. Un rechazo deja la publicación anterior visible y el candidato FAILED.

Se preservan todas las partes Parquet, columnas, tipos y filas anteriores de Reference y crosswalks, salvo los atributos físicos de productos y timestamps técnicos de extracción/ingesta. Se verifican diccionario físico e identidades. No se admite sustituir una Reference enriquecida por otra incompleta.

La transición actualmente admite los tres componentes derivados conocidos. Cambios de facts con esos componentes, componentes adicionales sin adapter, altas/bajas de filas, cambios comerciales u otros atributos anteriores requieren revalidación/rebuild específico y se bloquean. El refresh Reference sí admite productos nuevos; su promoción con derivados exige esa revalidación adicional.

Las versiones históricas siguen legibles. Se mantiene el límite existente de 32 niveles de ancestry: no se elude ni se declara compatible una cadena que lo exceda. Una preparación física incompleta se detecta y no activa el pointer; requiere revisión explícita, no sobrescritura silenciosa de versiones.

## Impacto SAP estático

El cambio remoto se limita a una columna adicional en el SELECT actual de OITM; no se ejecutó ninguna consulta ni benchmark remoto.

Se mantienen cuatro consultas de maestros, el SELECT 1 previo, los joins ya existentes de OSLP, la cantidad de filas y concurrencia secuencial máxima de uno. No se agregan consultas CUFD/UFD1 ni extracciones de facts. Se espera sólo el ancho adicional de una columna; el costo real no fue medido.

Localmente hay validaciones y hashes adicionales de Reference/crosswalk, no scans de facts. DuckDB del builder usa dos threads por conexión; las pruebas se ejecutaron secuencialmente, sin instalar dependencias.

## Preparación física sin activación

La API `reference_update.prepare_physical_reference` construye una candidata aislada desde observaciones previamente verificadas, sin usar el refresh completo ni activar pointers.

Recibe las rutas Reference/crosswalk del snapshot acreditado, observaciones con claves SAP exactas y fecha acreditada, y un root aislado. Copia todas las familias y modifica únicamente los seis atributos físicos de productos conciliados. Las identidades no conciliadas se reportan; no se crean canónicos ni se alteran crosswalks.

Se rechazan destinos dentro del Data Root compartido o de las fuentes. Se conservan preparaciones interrumpidas, se verifican destinos existentes y se reutiliza contenido idéntico sin reemplazar fechas selladas. La preparación no activa pointers. `publish_reference_only(..., prepare_only=True)` deja una candidata READY_TO_COMMIT; el wrapper durable `sales_foundation_promotion` admite esa candidata Reference-only y realiza CAS, journal, activación y verificación del reader.

La candidata real del 29/10 y sus límites están en el [cierre offline Reference/Foundation](../../../../../data/reports/telchi/reference-v2-foundation-offline-final-r2/report.md). El desfase real entre snapshots de datos y derivación está cubierto por regresión; no se abrió el catálogo compartido.

## Consumo analítico y herencia de ventas selladas

La dimensión física reutiliza `sales.commercial_line_amount_by.v1` y su permiso vigente; no crea otro motor de ventas ni amplía permisos.

- `group_by=physical_state` enriquece el universo guardado de líneas mediante `product_crosswalk` SAP → identidad canónica → producto SAP. Los LEFT JOIN preservan importes sin identidad o sin clasificación; duplicados de identidad se rechazan.
- Se preservan código original, categorías 0/4/5, ausencia, UNKNOWN e identidad faltante en auditoría. Sólo 1/2/3 son estados físicos explícitos. Cobertura por importe, líneas y productos distintos vendidos, no conteos del maestro completo.
- Métrica comercial existente: líneas de facturas activas en BS, sin IVA de línea y antes de NC/ajustes globales. Las NC documentales y el residuo con cabeceras son referencias separadas, nunca importes físicos prorrateados.
- Observación no implica vigencia histórica. El resultado acredita períodos, fecha de observación, publicación, Reference, snapshot y hashes de productos/crosswalk; presenta resultados válidos antes de sus límites.
- Ranking por productos y serie diaria son proyecciones del mismo universo. Un foco físico afecta la presentación, no elimina categorías del total conciliado. Las comparaciones admiten ventanas disjuntas verificadas, sin contar los días del intervalo intermedio.
- Una sucesora física de `SALES_FACTS_TRANSITION_V1` conserva exactamente contratos de facts, cobertura, evidencia y snapshots. El reader continúa usando archivos sellados y verifica sus hashes; no retorna a Atomic histórico por cambiar el tipo de envelope.

## Validación histórica y continuación

La evidencia histórica de la corrida sintética está en [pytest.xml](../../../../../data/reports/telchi/physical-product-classification-offline-v1/pytest.xml). El dictamen global permanece PARTIAL por un gate preexistente ajeno a estos cambios.

La suite completa Data Lake ejecutó 505 tests: 504 aprobados, uno fallido y cero omitidos. Los 32 tests nuevos pasan. El fallo es el scanner de readers por dos referencias preexistentes en `exploratory_sql/foundation.py` y `exploratory_sql/test_foundation.py`; no se modificaron esos paths ni se amplió su allowlist.

Se bloquearon conexiones de socket y construcción de la fuente HANA durante la corrida completa. Los escenarios nuevos cubren diccionario, persistencia de códigos, nulos/blancos/desconocidos, identidad SAP/legacy, cambios exclusivos, NOOP, contratos incompatibles, ocho componentes, readers, snapshots, fallos de preparación/precommit/commit/postcommit, rollback, reintento, idempotencia, historia y compare-and-swap.

No se inspeccionó ni modificó la publicación compartida vigente. La evidencia sintética no acredita que el siguiente refresh real cambiará exclusivamente la clasificación física: otros cambios del maestro pueden bloquear la promoción de forma segura.

Ese cierre histórico no determina el estado vigente. La integración posterior reutilizó capturas verificadas, sin releer HANA, y publicó con el wrapper canónico bajo instrucción operativa del responsable. Nuevas capturas o promociones conservan sus preflights, alcance y gates propios; consultar el [estado local](../status_actual.md).
